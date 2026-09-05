"""
Naija Job Alerts — Telegram bot MVP
Real-time job alerts for Nigeria, built on free RSS sources only.

ARCHITECTURE NOTE: this file now handles COMMANDS ONLY (/start, /keywords,
/location, /status, /pause, /resume). The actual feed-polling and alerting
runs separately via poll_once.py, triggered on a schedule by
.github/workflows/poll.yml — that half costs nothing to host at all (see
README). Running poll_jobs here AND via GitHub Actions would double-send
every alert, so it's been removed from this file's job queue.

This file still needs to run continuously somewhere to receive commands
(Telegram long-polling requires an always-on process) — see README for
free-hosting options for this specific piece.

Setup:
  1. pip install -r requirements.txt
  2. Get a free bot token from @BotFather on Telegram
  3. export JOB_BOT_TOKEN="your-token-here"
  4. python bot.py

Commands:
  /start                - register + instructions
  /help                  - list all commands
  /keywords <comma,list>- set keyword filters (e.g. "developer, sales, remote")
  /location <state>     - set a Nigerian state filter, or "any"
  /region <nigeria|remote|both> - filter Nigeria-only, remote-only, or both (default)
  /status                - show your current preferences
  /pause                 - stop receiving alerts
  /resume                - resume alerts
  /stats                 - (owner only) usage breakdown across all subscribers
"""
import logging
import asyncio

import urllib.request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import storage
from config import (
    BOT_TOKEN,
    NIGERIAN_STATES,
    ADMIN_CHAT_ID,
    HEALTHCHECK_PING_URL,
    HEALTHCHECK_PING_INTERVAL_MINUTES,
    CATEGORY_KEYWORDS,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    storage.upsert_user(chat_id)
    await update.message.reply_text(
        "Welcome to Naija Job Alerts 🇳🇬🌍\n\n"
        "I'll ping you the moment a matching job is posted — Nigeria-based AND "
        "legit remote/international roles, free, real-time, no spam.\n\n"
        "Set what you want:\n"
        "  /keywords developer, sales, remote\n"
        "  /location Lagos   (or /location any)\n"
        "  /region nigeria   (or /region remote, or /region both — default)\n\n"
        "Check anytime with /status. Pause with /pause, resume with /resume."
    )


async def set_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            "Send keywords separated by commas, e.g.:\n/keywords developer, accounting, remote\n\n"
            "Not sure what to type? Try /categories to pick from common options instead."
        )
        return
    keywords = " ".join(context.args)
    storage.upsert_user(chat_id, keywords=keywords)
    await update.message.reply_text(f"✅ Keywords set to: {keywords}")


async def categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"cat:{key}")]
        for key, (label, _) in CATEGORY_KEYWORDS.items()
    ]
    await update.message.reply_text(
        "Tap a category to set your keywords instantly — or use /keywords "
        "if you want something more specific.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # stops the loading spinner on the button

    key = query.data.split(":", 1)[1]
    if key not in CATEGORY_KEYWORDS:
        return
    label, keywords = CATEGORY_KEYWORDS[key]
    chat_id = update.effective_chat.id
    storage.upsert_user(chat_id, keywords=keywords)
    await query.edit_message_text(f"✅ {label} selected. Keywords set to: {keywords}")


async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            "Send a Nigerian state, e.g. /location Lagos — or /location any for everywhere."
        )
        return
    location = " ".join(context.args).strip()
    if location.lower() != "any" and location.title() not in NIGERIAN_STATES:
        await update.message.reply_text(
            "I didn't recognize that state. Try one like Lagos, Abuja, Rivers — or 'any'."
        )
        return
    storage.upsert_user(chat_id, location=location)
    await update.message.reply_text(f"✅ Location set to: {location}")


async def set_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    valid = {"nigeria", "remote", "both"}
    if not context.args or context.args[0].lower() not in valid:
        await update.message.reply_text(
            "Choose one: /region nigeria (Nigeria-based jobs only), "
            "/region remote (remote/international jobs only), "
            "or /region both (default — everything)."
        )
        return
    region = context.args[0].lower()
    storage.upsert_user(chat_id, region=region)
    labels = {
        "nigeria": "Nigeria-based jobs only 🇳🇬",
        "remote": "Remote/international jobs only 🌍",
        "both": "Both Nigeria and remote jobs 🇳🇬🌍",
    }
    await update.message.reply_text(f"✅ Region set to: {labels[region]}")


async def set_quiet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            "Set quiet hours (Nigeria time, WAT) when you don't want alerts, "
            "e.g. /quiet 22 7 for 10pm-7am.\n"
            "Matches during that window get held and sent as one digest when it ends.\n"
            "Send /quiet off to disable."
        )
        return

    if context.args[0].lower() == "off":
        storage.clear_quiet_hours(chat_id)
        await update.message.reply_text("✅ Quiet hours turned off — alerts can arrive any time.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /quiet <start_hour> <end_hour>, e.g. /quiet 22 7")
        return

    try:
        start_hour = int(context.args[0])
        end_hour = int(context.args[1])
        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
            raise ValueError
    except ValueError:
        await update.message.reply_text("Hours must be numbers 0-23, e.g. /quiet 22 7")
        return

    storage.upsert_user(chat_id, quiet_start=start_hour, quiet_end=end_hour)
    await update.message.reply_text(
        f"✅ Quiet hours set: {start_hour:02d}:00–{end_hour:02d}:00 WAT. "
        "Matches during that window will arrive as a digest right after it ends."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = storage.get_user(chat_id)
    if user is None:
        await update.message.reply_text("You're not registered yet — send /start first.")
        return
    state = "active ✅" if user["active"] else "paused ⏸️"
    quiet = (
        f"{user['quiet_start']:02d}:00–{user['quiet_end']:02d}:00 WAT"
        if user["quiet_start"] is not None and user["quiet_end"] is not None
        else "off"
    )
    await update.message.reply_text(
        f"Status: {state}\n"
        f"Keywords: {user['keywords'] or '(none set — matching everything)'}\n"
        f"Location: {user['location'] or '(none set — matching everywhere)'}\n"
        f"Region: {user['region'] or 'both'}\n"
        f"Quiet hours: {quiet}"
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    storage.set_active(chat_id, False)
    await update.message.reply_text("Paused. Send /resume anytime to start getting alerts again.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    storage.set_active(chat_id, True)
    await update.message.reply_text("Resumed — you'll get alerts again from the next check.")


async def deleteme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text(
            "This permanently deletes your saved keywords, location, and preferences — "
            "not just pausing alerts. This can't be undone.\n\n"
            "If you're sure, send: /deleteme confirm"
        )
        return
    storage.delete_user(chat_id)
    await update.message.reply_text(
        "Done — your data has been deleted. Send /start anytime if you want to come back."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/start — register\n"
        "/keywords developer, sales, remote — set what jobs to match\n"
        "/categories — pick keywords from tappable buttons instead\n"
        "/location Lagos — filter by state (or 'any')\n"
        "/region nigeria|remote|both — filter by job origin\n"
        "/quiet 22 7 — set quiet hours (WAT), or /quiet off\n"
        "/status — see your current settings\n"
        "/pause — stop alerts without losing settings\n"
        "/resume — start alerts again\n"
        "/deleteme confirm — permanently delete your data\n"
        "/help — this message"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if ADMIN_CHAT_ID is None or chat_id != ADMIN_CHAT_ID:
        return  # silently ignore for non-owners — don't reveal the command exists

    s = storage.get_usage_stats()
    lines = [
        f"👥 {s['total_users']} total ({s['active_users']} active, {s['paused_users']} paused)",
        "",
        "Region breakdown:",
    ]
    for region, count in s["region_breakdown"]:
        lines.append(f"  {region}: {count}")
    lines.append("")
    lines.append("Top keywords:")
    for kw, count in s["top_keywords"]:
        lines.append(f"  {kw}: {count}")
    lines.append("")
    lines.append("Top locations:")
    for loc, count in s["top_locations"]:
        lines.append(f"  {loc}: {count}")

    await update.message.reply_text("\n".join(lines))


async def send_heartbeat(context: ContextTypes.DEFAULT_TYPE):
    """
    Pings a free healthchecks.io URL on a schedule. If this bot process
    dies or hangs, the ping stops arriving and healthchecks.io alerts you —
    a standard free "dead man's switch" pattern that needs no exposed port,
    which matters since this runs via long-polling, not a web server.
    """
    if not HEALTHCHECK_PING_URL:
        return
    try:
        await asyncio.to_thread(urllib.request.urlopen, HEALTHCHECK_PING_URL, None, 10)
    except Exception:
        logger.exception("Heartbeat ping failed (network issue, not necessarily bot failure)")


def build_application():
    """Builds the Application with all command handlers registered, but
    doesn't start it — shared by main() (long-polling) and the Vercel
    webhook handler (one-shot per-request processing), which each drive
    the resulting Application differently."""
    if not BOT_TOKEN:
        raise SystemExit(
            "JOB_BOT_TOKEN environment variable is not set. "
            "Get a free token from @BotFather on Telegram and export it."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("keywords", set_keywords))
    app.add_handler(CommandHandler("categories", categories))
    app.add_handler(CallbackQueryHandler(category_callback, pattern="^cat:"))
    app.add_handler(CommandHandler("location", set_location))
    app.add_handler(CommandHandler("region", set_region))
    app.add_handler(CommandHandler("quiet", set_quiet))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("deleteme", deleteme))
    app.add_handler(CommandHandler("stats", stats))
    return app


def main():
    storage.init_db()
    app = build_application()

    if HEALTHCHECK_PING_URL:
        if app.job_queue is not None:
            app.job_queue.run_repeating(
                send_heartbeat,
                interval=HEALTHCHECK_PING_INTERVAL_MINUTES * 60,
                first=10,
            )
            logger.info("Heartbeat monitoring enabled (every %d min).", HEALTHCHECK_PING_INTERVAL_MINUTES)
        else:
            logger.warning(
                "HEALTHCHECK_PING_URL is set but job-queue isn't installed — "
                "run: pip install 'python-telegram-bot[job-queue]' to enable heartbeat monitoring."
            )

    logger.info("Command bot starting (feed polling runs separately via GitHub Actions).")
    app.run_polling()


if __name__ == "__main__":
    main()
