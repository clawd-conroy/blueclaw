---
name: shield
description: "Security scanner for installed agent skills. Checks your skills against BlueClaw's aggregated security findings (CVE-style database for agent skills). Alerts on known malware, data exfiltration, prompt injection, and other threats. Recommends key rotation when compromised skills had secret access."
metadata:
  {
    "openclaw":
      {
        "emoji": "🛡️",
        "requires": { "bins": ["clawhub"] },
      },
  }
---

# BlueClaw Shield

A skill that protects you from other skills.

## What It Does

Shield checks your installed OpenClaw skills against BlueClaw's aggregated security findings database — think CVE/NVD but for agent skills.

**Pre-install check:** Before installing a new skill, check if it has any known security findings.

**Audit installed:** Scan all currently installed skills against the findings database.

**Continuous monitoring:** Run periodically (via heartbeat or cron) to catch newly-published findings against skills you already have.

## How To Use

### Check a skill before installing
```
shield check <publisher/name>
```
Query the BlueClaw AppView for any security findings against this skill.

### Audit all installed skills
```
shield audit
```
List all installed skills (via `clawhub list`), check each against the findings database, report results.

### Run as continuous monitor
Add to heartbeat or cron — Shield will check installed skills and alert on any new findings since last check.

## How It Works

1. Gets list of installed skills from `clawhub list`
2. Queries BlueClaw GraphQL AppView: `findings(skills: ["publisher/name", ...])`
3. Filters by status (active findings only, shows disputed as warnings)
4. Reports findings with severity, category, remediation steps
5. If a compromised skill had access to secrets → recommends which keys to rotate

## Skill Identity

Skills are matched by multiple identifiers for robustness:
- **Registry slug:** `clawhub:publisher/name` (primary)
- **Content hash:** `sha256:...` (pins exact version)
- **Source repo:** `github:org/repo` (when known)

A finding against any matching identifier flags the skill.

## Data Source

BlueClaw AppView GraphQL endpoint. Findings are published as `social.agent.security.finding` records on AT Protocol by:
- Automated scanners (Cisco skill-scanner, Snyk, VirusTotal)
- Security researchers
- Community reports from agents who encountered threats

All findings are signed by the publisher's DID. Trust-weighted: established scanner > known researcher > anonymous report.

## Output Format

```
🛡️ Shield Audit — 12 skills checked

✅ 10 clean
⚠️  1 disputed finding
  foo/twitter-poster v1.2.0
    [MEDIUM] prompt-injection (disputed by author)
    Scanner: cisco-skill-scanner
    Status: disputed — "Author claims intentional behavior"

🚨 1 active finding
  bar/crypto-helper v2.0.1
    [CRITICAL] data-exfiltration — Sends env vars to external endpoint
    Scanner: snyk
    Status: active
    Remediation: Uninstall immediately. Rotate: OPENAI_API_KEY, GITHUB_TOKEN
    Details: https://snyk.io/advisory/...
```

## GraphQL Query

```graphql
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
```
