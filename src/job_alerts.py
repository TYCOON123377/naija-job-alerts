#!/usr/bin/env python3
"""Poll Nigerian job-board RSS feeds and alert on new matching listings."""
from __future__ import annotations

import argparse
import json
import logging
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import feedparser
import requests
import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("naija_job_alerts")


def load_config(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open() as f:
        return set(json.load(f))


def save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(sorted(seen), f, indent=2)


def matches(entry: dict[str, Any], keywords: list[str], locations: list[str]) -> bool:
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    if keywords and not any(k.lower() in text for k in keywords):
        return False
    if locations and not any(loc.lower() in text for loc in locations):
        return False
    return True


def fetch_matches(config: dict[str, Any], seen: set[str]) -> list[dict[str, str]]:
    keywords = config.get("keywords", [])
    locations = config.get("locations", [])
    found: list[dict[str, str]] = []

    for feed in config.get("feeds", []):
        name, url = feed["name"], feed["url"]
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:  # network/parse errors shouldn't kill the run
            log.warning("Failed to fetch feed %s (%s): %s", name, url, exc)
            continue

        for entry in parsed.entries:
            job_id = entry.get("id") or entry.get("link")
            if not job_id or job_id in seen:
                continue
            if matches(entry, keywords, locations):
                found.append(
                    {
                        "id": job_id,
                        "source": name,
                        "title": entry.get("title", "Untitled"),
                        "link": entry.get("link", ""),
                    }
                )
            seen.add(job_id)

    return found


def send_email(jobs: list[dict[str, str]]) -> None:
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    to_addr = os.environ.get("ALERT_EMAIL_TO")
    if not all([smtp_host, smtp_user, smtp_password, to_addr]):
        log.info("Email settings incomplete; skipping email alert.")
        return

    body = "\n\n".join(f"{j['title']} ({j['source']})\n{j['link']}" for j in jobs)
    msg = EmailMessage()
    msg["Subject"] = f"Naija Job Alerts: {len(jobs)} new matching job(s)"
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.set_content(body)

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
    log.info("Sent email alert for %d job(s).", len(jobs))


def send_telegram(jobs: list[dict[str, str]]) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.info("Telegram settings incomplete; skipping Telegram alert.")
        return

    text = "\n\n".join(f"{j['title']} ({j['source']})\n{j['link']}" for j in jobs)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
    resp.raise_for_status()
    log.info("Sent Telegram alert for %d job(s).", len(jobs))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default=REPO_ROOT / "config.yaml", type=Path,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print matches without sending alerts or updating the seen-jobs store",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    config = load_config(args.config)
    seen_path = REPO_ROOT / config.get("seen_jobs_file", "data/seen_jobs.json")
    seen = load_seen(seen_path)

    jobs = fetch_matches(config, seen)

    if not jobs:
        log.info("No new matching jobs found.")
        return 0

    log.info("Found %d new matching job(s).", len(jobs))
    for job in jobs:
        print(f"- [{job['source']}] {job['title']}\n  {job['link']}")

    if not args.dry_run:
        send_email(jobs)
        send_telegram(jobs)
        save_seen(seen_path, seen)

    return 0


if __name__ == "__main__":
    sys.exit(main())
