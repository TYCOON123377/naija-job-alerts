#!/usr/bin/env bash
# Bootstraps a local dev environment for Naija Job Alerts:
# creates a virtualenv, installs dependencies, and prepares config/data files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required but was not found on PATH." >&2
    exit 1
fi

VENV_DIR="$REPO_ROOT/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Installing dependencies ..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

mkdir -p "$REPO_ROOT/data"

if [ ! -f "$REPO_ROOT/.env" ]; then
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    echo "Created .env from .env.example — edit it to add SMTP/Telegram credentials."
else
    echo ".env already exists, leaving it untouched."
fi

chmod +x "$REPO_ROOT/src/job_alerts.py"

cat <<'EOF'

Setup complete.

Next steps:
  1. Edit config.yaml to set your keywords, locations, and RSS feeds.
  2. Edit .env to add SMTP and/or Telegram credentials (both optional;
     the script always prints matches to stdout regardless).
  3. Run a dry run:
       source .venv/bin/activate
       python src/job_alerts.py --dry-run
  4. Run for real (sends alerts and records seen jobs):
       python src/job_alerts.py

To check for new jobs automatically, add a cron entry, e.g. every 30 minutes:
  */30 * * * * cd REPO_ROOT && .venv/bin/python src/job_alerts.py >> /var/log/naija_job_alerts.log 2>&1

EOF
echo "(Replace REPO_ROOT above with: $REPO_ROOT)"
