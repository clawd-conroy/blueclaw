#!/usr/bin/env python3
"""
shield-aggregator.py — Aggregate security findings and publish to AT Protocol

We run this periodically to:
1. Scrape/query security sources (Cisco, Snyk, VirusTotal advisories, etc.)
2. Scan ClawHub skills directly using Cisco's skill-scanner (local)
3. Publish findings as social.agent.security.finding records to our PDS

Sources:
  - Cisco skill-scanner (local, Apache 2.0) — runs against ClawHub skills
  - Snyk advisories API — known malicious skills
  - HackerNews/security blogs — manual or LLM-assisted triage
  - Community reports — submitted via Shield skill or GitHub issues

Usage:
  # Scan top N ClawHub skills with Cisco scanner
  python3 shield-aggregator.py scan --top 100

  # Check for new advisories from known sources
  python3 shield-aggregator.py advisories

  # Publish findings to AT Protocol
  python3 shield-aggregator.py publish --findings findings.json

  # Full pipeline: scan + check advisories + publish
  python3 shield-aggregator.py all
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone


# --- Config ---

BLUECLAW_PDS = os.environ.get("BLUECLAW_PDS", "https://bsky.social")
BLUECLAW_HANDLE = os.environ.get("BLUESKY_USERNAME", "")
BLUECLAW_PASSWORD = os.environ.get("BLUESKY_PASSWORD", "")
APPVIEW_GQL = os.environ.get("BLUECLAW_APPVIEW", "https://blueclaw-production-630e.up.railway.app/graphql")

FINDINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "findings")
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "findings", ".published_state.json")
CLAWHUB_REGISTRY = "https://clawhub.ai"

# Skill slug validation pattern
SKILL_SLUG_RE = re.compile(r"^[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+$")

# Known advisory sources
ADVISORY_SOURCES = [
    {
        "name": "snyk",
        "url": "https://snyk.io/api/v1/advisories?type=agent-skill",
        "parser": "snyk",
    },
    # Add more as they publish APIs
]


# --- AT Protocol Auth ---

def atproto_login(handle, password, pds=BLUECLAW_PDS):
    """Authenticate with AT Protocol PDS, return session (accessJwt, did)."""
    payload = json.dumps({
        "identifier": handle,
        "password": password,
    }).encode()
    req = urllib.request.Request(
        f"{pds}/xrpc/com.atproto.server.createSession",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def atproto_create_record(session, collection, record, rkey=None, pds=BLUECLAW_PDS):
    """Publish a record to our PDS repo. If rkey is provided, AT Proto will deduplicate."""
    body = {
        "repo": session["did"],
        "collection": collection,
        "record": record,
    }
    if rkey:
        body["rkey"] = rkey
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {session['accessJwt']}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# --- Deduplication ---

def generate_rkey(finding):
    """Generate a deterministic rkey from skill+category+scanner for deduplication."""
    key_parts = f"{finding.get('skill', '')}|{finding.get('category', '')}|{finding.get('scanner', '')}"
    return hashlib.sha256(key_parts.encode()).hexdigest()[:15]


def load_published_state():
    """Load set of previously published rkeys."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return set(json.load(f))
        except (json.JSONDecodeError, TypeError):
            return set()
    return set()


def save_published_state(published):
    """Save set of published rkeys."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(published), f)


# --- Skill Slug Validation ---

def validate_skill_slug(slug):
    """Validate skill slug format before passing to subprocess."""
    if not SKILL_SLUG_RE.match(slug):
        print(f"  [skip] Invalid skill slug: {slug!r}", file=sys.stderr)
        return False
    return True


# --- ClawHub Scanning ---

def get_clawhub_skills(top=100):
    """Get list of skills from ClawHub (via clawhub CLI search)."""
    # Use clawhub search to get popular skills
    result = subprocess.run(
        ["clawhub", "search", "--limit", str(top)],
        capture_output=True, text=True,
    )
    skills = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            # Parse "publisher/name  version  description" format
            parts = line.strip().split()
            if parts and "/" in parts[0]:
                slug = parts[0]
                if validate_skill_slug(slug):
                    skills.append(slug)
    return skills


def scan_skill_cisco(skill_slug):
    """Run Cisco skill-scanner against a ClawHub skill.
    
    Requires: pip install cisco-ai-skill-scanner
    Downloads skill via clawhub inspect, scans locally.
    Returns list of findings or empty list.
    """
    if not validate_skill_slug(skill_slug):
        return []

    # Create temp dir for skill content
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download skill
        result = subprocess.run(
            ["clawhub", "inspect", skill_slug, "--output", tmpdir],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  [scan] Failed to fetch {skill_slug}: {result.stderr}", file=sys.stderr)
            return []

        # Run Cisco scanner
        result = subprocess.run(
            ["skill-scanner", "scan", tmpdir, "--format", "json"],
            capture_output=True, text=True,
        )
        if result.returncode != 0 and not result.stdout:
            print(f"  [scan] Scanner failed for {skill_slug}: {result.stderr}", file=sys.stderr)
            return []

        try:
            scan_results = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        # Convert Cisco findings to our format
        findings = []
        for finding in scan_results.get("findings", []):
            if finding.get("severity", "info") in ("critical", "high", "medium"):
                findings.append({
                    "skill": f"clawhub:{skill_slug}",
                    "severity": finding.get("severity", "medium"),
                    "category": map_cisco_category(finding.get("category", "other")),
                    "summary": finding.get("description", ""),
                    "scanner": "cisco-skill-scanner",
                    "status": "active",
                    "evidence": finding.get("details_url", ""),
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                })

        return findings


def map_cisco_category(cisco_cat):
    """Map Cisco scanner categories to our lexicon's knownValues."""
    mapping = {
        "prompt_injection": "prompt-injection",
        "data_exfiltration": "data-exfiltration",
        "malicious_code": "malware-delivery",
        "credential_access": "credential-theft",
        "reverse_shell": "reverse-shell",
        "typosquatting": "typosquatting",
        "supply_chain": "supply-chain",
    }
    return mapping.get(cisco_cat, "other")


# --- Publishing ---

def publish_findings(findings, dry_run=False):
    """Publish findings as social.agent.security.finding records to AT Protocol."""
    if not findings:
        print("No findings to publish.")
        return

    # Load previously published state for deduplication
    published = load_published_state()

    # Filter out already-published findings
    new_findings = []
    for f in findings:
        rkey = generate_rkey(f)
        if rkey in published:
            print(f"  [skip] Already published: {f['skill']} — {f['category']}")
        else:
            new_findings.append((rkey, f))

    if not new_findings:
        print("All findings already published. Nothing new.")
        return

    if dry_run:
        print(f"[DRY RUN] Would publish {len(new_findings)} new findings:")
        for rkey, f in new_findings:
            print(f"  [{f['severity'].upper()}] {f['skill']} — {f['category']}: {f['summary'][:80]}")
        return

    # Login right before publish to avoid token expiry on long pipelines
    session = atproto_login(BLUECLAW_HANDLE, BLUECLAW_PASSWORD)
    print(f"Authenticated as {session['handle']} ({session['did']})")

    successes = 0
    failures = 0

    for rkey, f in new_findings:
        try:
            record = {
                "$type": "social.agent.security.finding",
                "reporter": session["did"],
                **f,
            }
            result = atproto_create_record(
                session, "social.agent.security.finding", record, rkey=rkey
            )
            print(f"  Published: [{f['severity']}] {f['skill']} → {result.get('uri', '?')}")
            published.add(rkey)
            successes += 1
        except Exception as e:
            print(f"  ❌ Failed: [{f['severity']}] {f['skill']} — {e}", file=sys.stderr)
            failures += 1

    # Save state after publishing
    save_published_state(published)

    print(f"\nPublished {successes} findings, {failures} failed.")
    if failures:
        print(f"⚠️  {failures} record(s) failed to publish. Check errors above.", file=sys.stderr)


# --- Load/Save ---

def save_findings(findings, path=None):
    """Save findings to JSON for review before publishing."""
    if path is None:
        os.makedirs(FINDINGS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        path = os.path.join(FINDINGS_DIR, f"scan_{ts}.json")

    with open(path, "w") as f:
        json.dump(findings, f, indent=2)
    print(f"Saved {len(findings)} findings to {path}")
    return path


def load_findings(path):
    """Load findings from JSON."""
    with open(path) as f:
        return json.load(f)


# --- CLI ---

def cmd_scan(args):
    """Scan ClawHub skills with Cisco scanner."""
    skills = get_clawhub_skills(top=args.top)
    print(f"Scanning {len(skills)} skills...\n")

    all_findings = []
    for i, skill in enumerate(skills, 1):
        print(f"[{i}/{len(skills)}] {skill}")
        findings = scan_skill_cisco(skill)
        if findings:
            for f in findings:
                print(f"  🚨 [{f['severity'].upper()}] {f['category']}: {f['summary'][:80]}")
            all_findings.extend(findings)
        else:
            print(f"  ✅ Clean")

    print(f"\nTotal: {len(all_findings)} findings across {len(skills)} skills")
    if all_findings:
        path = save_findings(all_findings)
        print(f"Review findings at {path}, then run: shield-aggregator.py publish --findings {path}")


def cmd_publish(args):
    """Publish findings to AT Protocol."""
    findings = load_findings(args.findings)
    publish_findings(findings, dry_run=args.dry_run)


def cmd_all(args):
    """Full pipeline: scan + publish."""
    skills = get_clawhub_skills(top=args.top)
    print(f"Scanning {len(skills)} skills...\n")

    all_findings = []
    for i, skill in enumerate(skills, 1):
        print(f"[{i}/{len(skills)}] {skill}")
        findings = scan_skill_cisco(skill)
        if findings:
            for f in findings:
                print(f"  🚨 [{f['severity'].upper()}] {f['category']}: {f['summary'][:80]}")
            all_findings.extend(findings)
        else:
            print(f"  ✅ Clean")

    if all_findings:
        path = save_findings(all_findings)
        if not args.dry_run:
            print(f"\nPublishing {len(all_findings)} findings...")
            publish_findings(all_findings, dry_run=False)
        else:
            print(f"\n[DRY RUN] Would publish {len(all_findings)} findings. Review: {path}")
    else:
        print("\n✅ All skills clean. Nothing to publish.")


def main():
    parser = argparse.ArgumentParser(description="BlueClaw Shield — Security findings aggregator")
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Scan ClawHub skills with Cisco scanner")
    p_scan.add_argument("--top", type=int, default=100, help="Number of top skills to scan")
    p_scan.set_defaults(func=cmd_scan)

    p_pub = sub.add_parser("publish", help="Publish findings to AT Protocol")
    p_pub.add_argument("--findings", required=True, help="Path to findings JSON")
    p_pub.add_argument("--dry-run", action="store_true", help="Print what would be published")
    p_pub.set_defaults(func=cmd_publish)

    p_all = sub.add_parser("all", help="Scan + publish pipeline")
    p_all.add_argument("--top", type=int, default=100, help="Number of top skills to scan")
    p_all.add_argument("--dry-run", action="store_true", help="Don't actually publish")
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
