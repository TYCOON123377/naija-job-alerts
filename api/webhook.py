"""
Vercel serverless entrypoint for Telegram's webhook mode. Telegram POSTs
each update here instead of the bot long-polling for them — lets the
command bot (/keywords, /status, etc.) run on a stateless host with no
always-on process to babysit.

Vercel's filesystem is read-only except /tmp, and a fresh invocation may
land on a different instance with an empty /tmp — so user state can't
just live in a local file the way it does for poll_once.py (which runs on
a GitHub Actions checkout and commits data/jobs.db back to the repo).
Instead: pull the latest jobs.db from GitHub before handling the update,
push it back after only if this update actually changed something. See
github_sync.py.
"""
import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler

from telegram import Update

import github_sync
import storage
from bot import build_application
from config import DB_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


def _read_db_bytes():
    try:
        with open(DB_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return b""


async def _process(update_dict):
    sha = github_sync.pull_db()
    storage.init_db()
    before = _read_db_bytes()

    application = build_application()
    await application.initialize()
    try:
        update = Update.de_json(update_dict, application.bot)
        await application.process_update(update)
    finally:
        await application.shutdown()

    after = _read_db_bytes()
    if after != before:
        github_sync.push_db(sha)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if WEBHOOK_SECRET:
            token = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if token != WEBHOOK_SECRET:
                self.send_response(401)
                self.end_headers()
                return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"

        try:
            update_dict = json.loads(body)
            asyncio.run(_process(update_dict))
        except Exception:
            logger.exception("Failed to process Telegram update")

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")
