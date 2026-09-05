"""
Weekly "still here" digest — designed to be run once a week by a GitHub
Actions cron schedule (see .github/workflows/weekly_digest.yml).

Silence from the bot is indistinguishable from the bot being broken. This
sends a lightweight "still watching, nothing matched this week" message
ONLY to users who haven't received a real alert in the last 7 days —
someone getting alerts daily doesn't need filler, but someone whose
keywords are narrow enough that nothing has matched in a week benefits
from the reassurance that it's still working.

Usage:
  export JOB_BOT_TOKEN="..."
  python weekly_digest.py
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import Bot

import storage
from config import BOT_TOKEN
from telegram_utils import safe_send

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

STILL_HERE_MESSAGE = (
    "👋 Still watching for you — no new matches in the last week for your "
    "current filters.\n\n"
    "Nothing to do on your end, this is just confirming the bot's alive. "
    "Want to widen your search? /status shows your current settings, "
    "/keywords or /categories to adjust them."
)


def _needs_reassurance(user, cutoff):
    """True if this user hasn't gotten a real alert since before `cutoff`
    (SQLite CURRENT_TIMESTAMP strings sort/compare correctly as ISO text)."""
    last = user["last_notified_at"]
    if last is None:
        return True
    try:
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True  # malformed timestamp — err toward sending, not silence
    return last_dt < cutoff


async def run_once():
    if not BOT_TOKEN:
        raise SystemExit("JOB_BOT_TOKEN environment variable is not set.")

    storage.init_db()
    bot = Bot(token=BOT_TOKEN)

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    users = storage.get_active_users()

    sent = 0
    for user in users:
        if not _needs_reassurance(user, cutoff):
            continue
        if await safe_send(bot, user["chat_id"], STILL_HERE_MESSAGE):
            storage.update_last_notified(user["chat_id"])
            sent += 1

    logger.info("Weekly digest: sent to %d of %d active user(s).", sent, len(users))


if __name__ == "__main__":
    asyncio.run(run_once())
