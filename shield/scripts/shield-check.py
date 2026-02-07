#!/usr/bin/env python3
"""
shield-check.py — Check installed skills against BlueClaw security findings.

This is the thin client that agents run. Queries BlueClaw's GraphQL AppView
for any known security findings against your installed skills.

Note: When the AppView is unreachable, this tool fails closed — it reports
that skills could NOT be verified rather than silently passing them.

Usage:
  # Audit all installed skills
  python3 shield-check.py audit

  # Check a specific skill before installing
  python3 shield-check.py check publisher/name

  # JSON output (for programmatic use)
  python3 shield-check.py audit --json
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
query ShieldCheck($skills: [String!]!) {
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


def get_installed_skills():
    """Get installed skills from clawhub list."""
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
    # Prefix with clawhub: for registry-qualified lookup
    qualified = [f"clawhub:{s}" for s in skill_names]

    payload = json.dumps({
        "query": FINDINGS_QUERY,
        "variables": {"skills": qualified + skill_names},  # check both qualified and bare
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
        # Fail closed: report that we could NOT verify, don't silently pass
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
    """Print human-readable shield report."""
    if findings is None:
        # Fail closed: unreachable means NOT verified
        print("🛡️ Shield Audit — ⚠️ Could not reach findings database")
        print("   Your skills were NOT checked. Try again later.")
        return 1

    # Group findings by skill
    by_skill = {}
    for f in findings:
        skill = f["skill"].replace("clawhub:", "")
        by_skill.setdefault(skill, []).append(f)

    # Sort findings by severity
    for skill in by_skill:
        by_skill[skill].sort(key=lambda f: severity_rank(f["severity"]))

    clean = [s for s in skills if s["name"] not in by_skill]
    flagged = [s for s in skills if s["name"] in by_skill]

    print(f"🛡️ Shield Audit — {len(skills)} skills checked\n")

    if not flagged:
        print(f"✅ All {len(clean)} skills clean. No known security findings.")
        return 0

    # Show flagged skills
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

    # Summary
    print(f"───────────────────────────")
    print(f"✅ {len(clean)} clean | {severity_icon('critical')} {len(flagged)} with findings")
    if has_critical:
        print(f"\n⚠️  CRITICAL findings detected. Review and take action immediately.")

    return 2 if has_critical else 1


def cmd_audit(args):
    """Audit all installed skills."""
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


def cmd_check(args):
    """Check a specific skill."""
    findings = query_findings([args.skill])

    if args.json:
        print(json.dumps({"skill": args.skill, "findings": findings or []}, indent=2))
        return

    if findings is None:
        print(f"⚠️  Could not reach BlueClaw AppView")
        sys.exit(1)

    if not findings:
        print(f"✅ {args.skill} — No known security findings. Safe to install.")
    else:
        findings.sort(key=lambda f: severity_rank(f["severity"]))
        worst = findings[0]["severity"]
        print(f"{severity_icon(worst)} {args.skill} — {len(findings)} finding(s):\n")
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


def main():
    parser = argparse.ArgumentParser(description="🛡️ BlueClaw Shield — Check skills against security findings")
    sub = parser.add_subparsers(dest="command")

    p_audit = sub.add_parser("audit", help="Audit all installed skills")
    p_audit.add_argument("--json", action="store_true", help="JSON output")
    p_audit.set_defaults(func=cmd_audit)

    p_check = sub.add_parser("check", help="Check a specific skill before installing")
    p_check.add_argument("skill", help="Skill slug (e.g. publisher/name)")
    p_check.add_argument("--json", action="store_true", help="JSON output")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
