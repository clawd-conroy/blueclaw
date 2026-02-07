---
name: blueclaw
description: "Security tooling for agent skills. Scan installed skills against BlueClaw's aggregated security findings database. Alerts on known malware, data exfiltration, prompt injection, and other threats. Recommends key rotation when compromised skills had secret access."
metadata:
  {
    "openclaw":
      {
        "emoji": "🦞",
        "requires": { "bins": ["clawhub"] },
      },
  }
---

# BlueClaw

Security tooling for agent skills — a CLI with subcommands.

## Subcommands

### `blueclaw scan`

Check your installed skills against BlueClaw's aggregated security findings database — think CVE/NVD but for agent skills.

**Scan all installed skills:**
```
blueclaw scan
```
Lists all installed skills (via `clawhub list`), checks each against the findings database, reports results.

**Check a specific skill before installing:**
```
blueclaw scan publisher/name
```
Query the BlueClaw AppView for any security findings against this skill.

**Scan a local skills directory:**
```
blueclaw scan /path/to/skills
```
Finds skills by looking for `SKILL.md` files in subdirectories.

**JSON output:**
```
blueclaw scan --json
```

### `blueclaw publish` *(coming soon)*

Publish a `social.agent.skill.identity` record to your PDS, declaring authorship and metadata for a skill you maintain.

### `blueclaw review` *(coming soon)*

Submit or view security findings for a skill. Community-driven security reporting.

### `blueclaw verify` *(coming soon)*

Verify a skill's identity and source integrity — check that the author's DID matches, content hashes are valid, and no tampering has occurred.

## How `scan` Works

1. Gets list of installed skills from `clawhub list` (or scans a directory)
2. Queries BlueClaw GraphQL AppView: `findings(skills: [...])`
3. Filters by status (active findings only, shows disputed as warnings)
4. Reports findings with severity, category, remediation steps
5. Fails closed — if the AppView is unreachable, reports skills as NOT verified

## Exit Codes

- `0` — All skills clean
- `1` — Warnings or couldn't reach AppView
- `2` — Critical/high severity findings detected

## Internal Tooling

The `shield-aggregator.py` script is internal infrastructure that runs on Railway as a cron job. It scans ClawHub skills using Cisco's skill-scanner and publishes `social.agent.security.finding` records to the BlueClaw PDS. See `DEPLOY.md` for Railway setup.
