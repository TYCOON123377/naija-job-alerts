"""
One-shot poll — designed to be run by a GitHub Actions cron schedule
instead of an always-on process, so the alerting half of the bot costs
nothing to host (no server, no worker dyno).

Runs once, does one fetch/match/send cycle, and exits. State (users,
seen jobs) lives in data/jobs.db, which the GitHub Actions workflow commits
back to the repo after each run — see .github/workflows/poll.yml.

Usage:
  export JOB_BOT_TOKEN="..."
  python poll_once.py
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from telegram import Bot

import storage
from config import BOT_TOKEN, DIGEST_THRESHOLD, SEND_DELAY_SECONDS
from fetcher import fetch_new_jobs
from matcher import (
    job_matches_user,
    format_job_message,
    format_digest_message,
    is_fresh,
    is_in_quiet_hours,
)
from telegram_utils import safe_send

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WAT = timezone(timedelta(hours=1))  # West Africa Time, UTC+1, no DST


async def _send_matches(bot, user, matches):
    """Sends a user's matches (digest above threshold, individual below),
    then clears their pending queue and stamps last_notified_at on success.
    Leaves the pending queue untouched on failure so nothing is lost."""
    chat_id = user["chat_id"]

    if len(matches) <= DIGEST_THRESHOLD:
        ok = True
        for job in matches:
            ok = await safe_send(bot, chat_id, format_job_message(job))
            if not ok:
                break
            await asyncio.sleep(SEND_DELAY_SECONDS)
    else:
        ok = await safe_send(bot, chat_id, format_digest_message(matches))

    if ok:
        storage.clear_pending_alerts(chat_id)
        storage.update_last_notified(chat_id)
    return ok


async def run_once():
    if not BOT_TOKEN:
        raise SystemExit("JOB_BOT_TOKEN environment variable is not set.")

    storage.init_db()
    bot = Bot(token=BOT_TOKEN)

    jobs = fetch_new_jobs()

    if not storage.has_any_seen_jobs():
        storage.mark_jobs_seen_bulk([j["guid"] for j in jobs])
        logger.info("First run — baselined %d existing jobs, no alerts sent.", len(jobs))
        return

    new_jobs = [j for j in jobs if not storage.is_job_seen(j["guid"])]
    fresh_new_jobs = [j for j in new_jobs if is_fresh(j)]

    logger.info(
        "Fetched %d jobs, %d new, %d fresh-and-new.",
        len(jobs), len(new_jobs), len(fresh_new_jobs),
    )

    wat_hour = datetime.now(WAT).hour
    users = storage.get_active_users()
    sent_count = 0
    queued_count = 0

    for user in users:
        new_matches = [job for job in fresh_new_jobs if job_matches_user(job, user)]

        if is_in_quiet_hours(user, wat_hour):
            for job in new_matches:
                storage.queue_pending_alert(user["chat_id"], json.dumps(job))
            queued_count += len(new_matches)
            continue

        pending_rows = storage.get_pending_alerts(user["chat_id"])
        pending_jobs = [json.loads(r["job_json"]) for r in pending_rows]
        all_matches = pending_jobs + new_matches

        if not all_matches:
            continue

        if await _send_matches(bot, user, all_matches):
            sent_count += 1

    if queued_count:
        logger.info("Queued %d match(es) for users currently in quiet hours.", queued_count)
    if sent_count:
        logger.info("Sent alerts to %d user(s) this run.", sent_count)

    for job in new_jobs:
        storage.mark_job_seen(job["guid"])
    storage.prune_old_seen_jobs()

    logger.info("Poll cycle complete.")


if __name__ == "__main__":
    asyncio.run(run_once())
