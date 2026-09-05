"""
Syncs data/jobs.db with GitHub so the webhook-hosted command bot (a
stateless Vercel function — no persistent disk between invocations) shares
the same user/job state as poll_once.py, which runs on GitHub Actions and
commits jobs.db back to the repo after every poll. Without this, a
keyword/location change made through the bot would only ever live in that
one ephemeral invocation, and poll_once.py would keep alerting against
stale preferences.

Requires GITHUB_TOKEN (a fine-grained PAT, Contents: read+write, scoped
to this repo) and GITHUB_REPO ("owner/repo") as environment variables.
"""
import base64
import json
import logging
import os
import urllib.error
import urllib.request

from config import DB_PATH

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
DB_REPO_PATH = "data/jobs.db"

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DB_REPO_PATH}"


def _request(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def pull_db():
    """Downloads the latest committed jobs.db to DB_PATH. Returns the
    blob's sha (needed to push an update without a conflict), or None if
    the file doesn't exist on GitHub yet (first-ever deploy)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise RuntimeError("GITHUB_TOKEN / GITHUB_REPO not set")

    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    try:
        info = _request("GET", f"{API_URL}?ref={GITHUB_BRANCH}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

    with open(DB_PATH, "wb") as f:
        f.write(base64.b64decode(info["content"]))
    return info["sha"]


def push_db(sha, message="Update jobs.db via bot command"):
    """Uploads the local jobs.db back to GitHub. Retries once, re-fetching
    sha, if the poll workflow committed in between (409 conflict)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise RuntimeError("GITHUB_TOKEN / GITHUB_REPO not set")

    with open(DB_PATH, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    body = {"message": message, "content": content_b64, "branch": GITHUB_BRANCH}
    if sha:
        body["sha"] = sha

    try:
        _request("PUT", API_URL, body)
    except urllib.error.HTTPError as e:
        if e.code == 409:
            logger.info("Push conflict (concurrent write) — retrying once with fresh sha.")
            latest = _request("GET", f"{API_URL}?ref={GITHUB_BRANCH}")
            body["sha"] = latest["sha"]
            _request("PUT", API_URL, body)
        else:
            raise
