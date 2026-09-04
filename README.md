# Naija Job Alerts

Polls Nigerian job-board RSS feeds for listings matching your keywords and
locations, then notifies you by email and/or Telegram — skipping anything
already alerted on.

## Setup

```bash
./setup_naija_job_alerts.sh
```

This creates a `.venv`, installs dependencies from `requirements.txt`, and
copies `.env.example` to `.env` (edit it to add credentials).

## Configuration

- `config.yaml` — keywords, locations, and the list of RSS feeds to poll.
- `.env` — optional SMTP and Telegram credentials for alerts. If left blank,
  matches are still printed to stdout.

## Usage

```bash
source .venv/bin/activate
python src/job_alerts.py --dry-run   # preview matches, no alerts sent
python src/job_alerts.py             # send alerts, record seen jobs
```

## Automating it

Add a cron entry to check periodically, e.g. every 30 minutes:

```
*/30 * * * * cd /path/to/naija-job-alerts && .venv/bin/python src/job_alerts.py >> /var/log/naija_job_alerts.log 2>&1
```

## How it works

`src/job_alerts.py` fetches each configured RSS feed with `feedparser`,
keeps entries whose title/summary contain a configured keyword (and, if set,
a configured location), and skips anything whose link/id is already in
`data/seen_jobs.json`. New matches are printed, emailed (if SMTP settings are
present), and sent to Telegram (if bot settings are present), then recorded
as seen so they aren't re-alerted next run.
