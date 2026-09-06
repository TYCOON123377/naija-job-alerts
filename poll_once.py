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
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from telegram import Bot

import storage
from config import (
    BOT_TOKEN,
    DIGEST_THRESHOLD,
    GREENHOUSE_BOARDS,
    HEALTHCHECK_PING_URL,
    JOB_FEEDS,
    RECENT_JOBS_WINDOW_HOURS,
    SEND_DELAY_SECONDS,
    TELEGRAM_CHANNELS,
)
from fetcher import fetch_greenhouse_jobs, fetch_new_jobs, fetch_telegram_jobs
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


def _due(sources, now, key_fn):
    """Sources due to be pulled this run — everything without a
    min_interval_minutes, plus any throttled source (like Jobicy's feed or
    the Greenhouse boards, whose terms ask for infrequent polling rather
    than one hit every 15 minutes) whose interval has actually elapsed
    since its last fetch. Shared between config.JOB_FEEDS (keyed by url)
    and config.GREENHOUSE_BOARDS (keyed by slug) via key_fn."""
    due = []
    for source in sources:
        min_interval = source.get("min_interval_minutes")
        if min_interval:
            last = storage.get_feed_last_fetched(key_fn(source))
            if last and (now - last) < min_interval * 60:
                continue
        due.append(source)
    return due


def _feed_key(feed):
    return feed["url"]


def _board_key(board):
    return f"greenhouse:{board['slug']}"


def _send_heartbeat():
    """Pings a free healthchecks.io URL at the end of a successful run —
    a dead-man's-switch so a silently-broken cron (expired GITHUB_TOKEN,
    a source that starts erroring every run, GitHub Actions itself having
    an outage) gets noticed instead of just... not alerting anyone,
    indefinitely, with nothing to notice. Called only on success, not from
    a finally block, so a real failure correctly shows up as a missed
    check-in on healthchecks.io's side."""
    if not HEALTHCHECK_PING_URL:
        return
    try:
        urllib.request.urlopen(HEALTHCHECK_PING_URL, timeout=10)
    except urllib.error.URLError:
        logger.exception("Heartbeat ping failed (network issue, not necessarily a real failure).")


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

    now = time.time()
    feeds = _due(JOB_FEEDS, now, _feed_key)
    boards = _due(GREENHOUSE_BOARDS, now, _board_key)
    skipped = (len(JOB_FEEDS) - len(feeds)) + (len(GREENHOUSE_BOARDS) - len(boards))
    if skipped:
        logger.info("Skipping %d throttled source(s) not due yet this run.", skipped)

    jobs = fetch_new_jobs(feeds) + fetch_greenhouse_jobs(boards) + fetch_telegram_jobs(TELEGRAM_CHANNELS)
    storage.store_recent_jobs(jobs)
    storage.prune_old_recent_jobs(RECENT_JOBS_WINDOW_HOURS)
    for feed in feeds:
        if feed.get("min_interval_minutes"):
            storage.set_feed_last_fetched(_feed_key(feed), now)
    for board in boards:
        if board.get("min_interval_minutes"):
            storage.set_feed_last_fetched(_board_key(board), now)

    if not storage.has_any_seen_jobs():
        storage.mark_jobs_seen_bulk([j["guid"] for j in jobs])
        logger.info("First run — baselined %d existing jobs, no alerts sent.", len(jobs))
        _send_heartbeat()
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
    _send_heartbeat()


if __name__ == "__main__":
    asyncio.run(run_once())
