"""
Shared Telegram send helper. Centralizes the blocked-user/deleted-chat
handling so poll_once.py and weekly_digest.py don't duplicate it.
"""
import logging

from telegram.error import Forbidden, BadRequest

import storage

logger = logging.getLogger(__name__)


async def safe_send(bot, chat_id, text, parse_mode="HTML", disable_web_page_preview=True):
    """
    Sends one message. Returns True on success, False on failure.
    Auto-pauses the user on Forbidden (blocked the bot) or BadRequest
    (chat no longer exists) — both mean every future send to this chat_id
    will fail identically, so retrying forever just wastes cycles and
    drowns real errors in expected noise. Any other exception (network
    blip, transient Telegram error) is logged but doesn't deactivate
    anyone — a bad moment for the API shouldn't cost someone their
    subscription.
    """
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
        return True
    except Forbidden:
        storage.set_active(chat_id, False)
        logger.info("Auto-paused chat_id %s (blocked the bot).", chat_id)
        return False
    except BadRequest as e:
        storage.set_active(chat_id, False)
        logger.info("Auto-paused chat_id %s (chat unavailable: %s).", chat_id, e)
        return False
    except Exception:
        logger.exception("Failed to send message to %s", chat_id)
        return False
