# Shield Scanner — Railway Cron Service

## Deploy

1. Connect `clawd-conroy/blueclaw` repo to Railway
2. Create new service → Dockerfile → point to `shield/Dockerfile`
3. Set as **Cron Service** with schedule (e.g. `0 */6 * * *` = every 6 hours)

## Environment Variables

Set these as **Railway secrets** (not plaintext in config):

```
BLUESKY_USERNAME=blueclaw-shield.bsky.social
BLUESKY_PASSWORD=<app password — generate at bsky.app/settings/app-passwords>
BLUECLAW_APPVIEW=https://api.blueclaw.org/graphql
```

## Override CMD

- Dry run (default): `all --top 100 --dry-run`
- Live: `all --top 100`
- Scan only: `scan --top 200`
- Publish existing: `publish --findings /app/findings/scan_2026-02-07.json`

## Cost Estimate

- ~10-15 min per 100 skills scanned
- At every 6 hours: ~60 min/day compute
- Railway: ~$0.03/day → **<$1/mo**
