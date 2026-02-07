#!/usr/bin/env python3
"""
blueclaw.py — BlueClaw CLI for agent skill security.

Subcommands:
  scan    Check installed skills against BlueClaw security findings.

Future subcommands (not yet implemented):
  publish   Publish a skill identity record to your PDS.
  review    Submit or view security findings for a skill.
  verify    Verify a skill's identity and source integrity.

Usage:
  # Scan all installed skills
  python3 blueclaw.py scan

  # Scan a specific skill before installing
  python3 blueclaw.py scan publisher/name

  # Scan a local skills directory
  python3 blueclaw.py scan /path/to/skills

  # JSON output
  python3 blueclaw.py scan --json
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request

APPVIEW_GQL = os.environ.get(
    "BLUECLAW_APPVIEW",
    "https://blueclaw-production-630e.up.railway.app/graphql"
)

# Warn if AppView URL is not HTTPS
if not APPVIEW_GQL.startswith("https://"):
    print(
        f"⚠️  WARNING: BLUECLAW_APPVIEW is not HTTPS: {APPVIEW_GQL}\n"
        f"   Findings data may be intercepted or tampered with.",
        file=sys.stderr,
    )

# GraphQL query for security findings
FINDINGS_QUERY = """
query BlueclawScan($skills: [String!]!) {
  securityFindings(skills: $skills, status: [ACTIVE, DISPUTED]) {
    skill
    skillVersion
    severity
    category
    summary
    scanner
    status
    statusNote
    remediation
    affectedKeys
    evidence
    createdAt
  }
}
"""


def get_installed_skills(path=None):
    """Get installed skills from clawhub list or by scanning a directory."""
    if path and os.path.isdir(path):
        # Scan a directory for skills (look for SKILL.md files)
        skills = []
        for entry in os.listdir(path):
            skill_md = os.path.join(path, entry, "SKILL.md")
            if os.path.isfile(skill_md):
                skills.append({"name": entry, "version": "local"})
        return skills

    result = subprocess.run(
        ["clawhub", "list"],
        capture_output=True, text=True,
    )
    skills = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            parts = line.strip().split()
            if parts:
                skills.append({
                    "name": parts[0],
                    "version": parts[1] if len(parts) > 1 else "unknown",
                })
    return skills


def query_findings(skill_names):
    """Query BlueClaw AppView for security findings."""
    qualified = [f"clawhub:{s}" for s in skill_names]

    payload = json.dumps({
        "query": FINDINGS_QUERY,
        "variables": {"skills": qualified + skill_names},
    }).encode()

    req = urllib.request.Request(
        APPVIEW_GQL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("data", {}).get("securityFindings", [])
    except Exception as e:
        print(f"⚠️  Could not reach BlueClaw AppView: {e}", file=sys.stderr)
        print(f"   URL: {APPVIEW_GQL}", file=sys.stderr)
        return None


def severity_icon(sev):
    icons = {
        "critical": "🚨",
        "high": "🔴",
        "medium": "🟡",
        "low": "🔵",
        "info": "ℹ️",
    }
    return icons.get(sev, "❓")


def severity_rank(sev):
    ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return ranks.get(sev, 5)


def print_report(skills, findings):
    """Print human-readable scan report."""
    if findings is None:
        print("🦞 BlueClaw Scan — ⚠️ Could not reach findings database")
        print("   Your skills were NOT checked. Try again later.")
        return 1

    by_skill = {}
    for f in findings:
        skill = f["skill"].replace("clawhub:", "")
        by_skill.setdefault(skill, []).append(f)

    for skill in by_skill:
        by_skill[skill].sort(key=lambda f: severity_rank(f["severity"]))

    clean = [s for s in skills if s["name"] not in by_skill]
    flagged = [s for s in skills if s["name"] in by_skill]

    print(f"🦞 BlueClaw Scan — {len(skills)} skills checked\n")

    if not flagged:
        print(f"✅ All {len(clean)} skills clean. No known security findings.")
        return 0

    has_critical = False
    for skill in flagged:
        skill_findings = by_skill[skill["name"]]
        worst = skill_findings[0]["severity"]
        if worst in ("critical", "high"):
            has_critical = True

        print(f"{severity_icon(worst)} {skill['name']} v{skill['version']}")
        for f in skill_findings:
            status_str = ""
            if f["status"] == "disputed":
                status_str = f" (disputed: {f.get('statusNote', 'contested by author')})"
            print(f"    [{f['severity'].upper()}] {f['category']}{status_str}")
            print(f"    {f['summary'][:120]}")
            print(f"    Scanner: {f.get('scanner', 'unknown')}")
            if f.get("remediation"):
                print(f"    Remediation: {f['remediation'][:120]}")
            if f.get("affectedKeys"):
                print(f"    🔑 Rotate: {', '.join(f['affectedKeys'])}")
            if f.get("evidence"):
                print(f"    Details: {f['evidence']}")
            print()

    print(f"───────────────────────────")
    print(f"✅ {len(clean)} clean | {severity_icon('critical')} {len(flagged)} with findings")
    if has_critical:
        print(f"\n⚠️  CRITICAL findings detected. Review and take action immediately.")

    return 2 if has_critical else 1


def cmd_scan(args):
    """Scan skills for known security findings."""
    if args.target:
        if os.path.isdir(args.target):
            skills = get_installed_skills(path=args.target)
            if not skills:
                print(f"No skills found in {args.target}")
                return
        else:
            # Treat as a single skill name
            findings = query_findings([args.target])
            if args.json:
                print(json.dumps({"skill": args.target, "findings": findings or []}, indent=2))
                return
            if findings is None:
                print(f"⚠️  Could not reach BlueClaw AppView")
                sys.exit(1)
            if not findings:
                print(f"✅ {args.target} — No known security findings.")
            else:
                findings.sort(key=lambda f: severity_rank(f["severity"]))
                worst = findings[0]["severity"]
                print(f"{severity_icon(worst)} {args.target} — {len(findings)} finding(s):\n")
                for f in findings:
                    print(f"  [{f['severity'].upper()}] {f['category']}: {f['summary'][:120]}")
                    if f.get("remediation"):
                        print(f"  Remediation: {f['remediation'][:120]}")
                    print()
                if worst in ("critical", "high"):
                    print(f"🚨 Do NOT install this skill.")
                    sys.exit(2)
                else:
                    print(f"⚠️  Proceed with caution.")
                    sys.exit(1)
            return
    else:
        skills = get_installed_skills()
        if not skills:
            print("No skills installed (or clawhub not available).")
            return

    skill_names = [s["name"] for s in skills]
    findings = query_findings(skill_names)

    if args.json:
        print(json.dumps({
            "skills": skills,
            "findings": findings or [],
            "checked_at": __import__("datetime").datetime.now().isoformat(),
        }, indent=2))
    else:
        sys.exit(print_report(skills, findings))


def main():
    parser = argparse.ArgumentParser(
        description="🦞 BlueClaw — Security tooling for agent skills",
        prog="blueclaw",
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Check skills against known security findings")
    p_scan.add_argument("target", nargs="?", help="Skill name, path to skills dir, or omit to scan all installed")
    p_scan.add_argument("--json", action="store_true", help="JSON output")
    p_scan.set_defaults(func=cmd_scan)

    # Future subcommands (documented, not implemented)
    sub.add_parser("publish", help="Publish a skill identity record (coming soon)")
    sub.add_parser("review", help="Submit or view security findings (coming soon)")
    sub.add_parser("verify", help="Verify skill identity and source integrity (coming soon)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.command in ("publish", "review", "verify"):
        print(f"🦞 `blueclaw {args.command}` is not yet implemented. Stay tuned!")
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
