"""
SQLite storage for Naija Job Alerts.

Tables:
  users(chat_id PRIMARY KEY, keywords, location, active)
  seen_jobs(guid PRIMARY KEY, first_seen)
"""
import sqlite3
from contextlib import contextmanager

from config import DB_PATH


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                keywords TEXT DEFAULT '',
                location TEXT DEFAULT '',
                region TEXT DEFAULT 'both',
                active INTEGER DEFAULT 1,
                quiet_start INTEGER DEFAULT NULL,
                quiet_end INTEGER DEFAULT NULL,
                last_notified_at TEXT DEFAULT NULL,
                onboarding_step TEXT DEFAULT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                guid TEXT PRIMARY KEY,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                job_json TEXT NOT NULL,
                queued_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feed_state (
                url TEXT PRIMARY KEY,
                last_fetched_epoch INTEGER
            )
        """)
        # Migrations for DBs created before these columns existed.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "region" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN region TEXT DEFAULT 'both'")
        if "quiet_start" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN quiet_start INTEGER DEFAULT NULL")
        if "quiet_end" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN quiet_end INTEGER DEFAULT NULL")
        if "last_notified_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN last_notified_at TEXT DEFAULT NULL")
        if "onboarding_step" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN onboarding_step TEXT DEFAULT NULL")
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def upsert_user(chat_id, keywords=None, location=None, region=None, quiet_start=None, quiet_end=None):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (chat_id, keywords, location, region, active, quiet_start, quiet_end) "
                "VALUES (?, ?, ?, ?, 1, ?, ?)",
                (chat_id, keywords or "", location or "", region or "both", quiet_start, quiet_end),
            )
        else:
            if keywords is not None:
                conn.execute("UPDATE users SET keywords=? WHERE chat_id=?", (keywords, chat_id))
            if location is not None:
                conn.execute("UPDATE users SET location=? WHERE chat_id=?", (location, chat_id))
            if region is not None:
                conn.execute("UPDATE users SET region=? WHERE chat_id=?", (region, chat_id))
            if quiet_start is not None:
                conn.execute("UPDATE users SET quiet_start=? WHERE chat_id=?", (quiet_start, chat_id))
            if quiet_end is not None:
                conn.execute("UPDATE users SET quiet_end=? WHERE chat_id=?", (quiet_end, chat_id))
        conn.commit()


def clear_quiet_hours(chat_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET quiet_start=NULL, quiet_end=NULL WHERE chat_id=?", (chat_id,))
        conn.commit()


def set_active(chat_id, active: bool):
    with get_conn() as conn:
        conn.execute("UPDATE users SET active=? WHERE chat_id=?", (1 if active else 0, chat_id))
        conn.commit()


def delete_user(chat_id):
    """Full erasure — removes the user's row entirely, not just a pause.
    Also clears any queued quiet-hours alerts for them (see pending_alerts)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE chat_id=?", (chat_id,))
        conn.execute("DELETE FROM pending_alerts WHERE chat_id=?", (chat_id,))
        conn.commit()


def get_active_users():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE active=1").fetchall()


def get_user(chat_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()


def is_job_seen(guid):
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM seen_jobs WHERE guid=?", (guid,)).fetchone()
        return row is not None


def mark_job_seen(guid):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO seen_jobs (guid) VALUES (?)", (guid,))
        conn.commit()


def has_any_seen_jobs():
    """False only on a truly fresh database — used to decide whether to
    baseline silently on first run instead of alerting on the whole feed."""
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM seen_jobs LIMIT 1").fetchone()
        return row is not None


def mark_jobs_seen_bulk(guids):
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_jobs (guid) VALUES (?)",
            [(g,) for g in guids],
        )
        conn.commit()


def prune_old_seen_jobs(keep_last=5000):
    """Keep the seen_jobs table from growing forever on a free-tier disk."""
    with get_conn() as conn:
        conn.execute("""
            DELETE FROM seen_jobs WHERE guid NOT IN (
                SELECT guid FROM seen_jobs ORDER BY first_seen DESC LIMIT ?
            )
        """, (keep_last,))
        conn.commit()


def queue_pending_alert(chat_id, job_json):
    """Used during a user's quiet hours: hold a matched job instead of
    sending immediately, to be flushed as a digest once quiet hours end."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pending_alerts (chat_id, job_json) VALUES (?, ?)",
            (chat_id, job_json),
        )
        conn.commit()


def get_pending_alerts(chat_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM pending_alerts WHERE chat_id=? ORDER BY queued_at", (chat_id,)
        ).fetchall()


def clear_pending_alerts(chat_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM pending_alerts WHERE chat_id=?", (chat_id,))
        conn.commit()


def update_last_notified(chat_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET last_notified_at=CURRENT_TIMESTAMP WHERE chat_id=?", (chat_id,)
        )
        conn.commit()


def set_onboarding_step(chat_id, step):
    """step is one of 'keywords', 'location', 'region', or None (not in
    onboarding — either finished it, or a pre-existing user from before
    this feature who never needed to)."""
    with get_conn() as conn:
        conn.execute("UPDATE users SET onboarding_step=? WHERE chat_id=?", (step, chat_id))
        conn.commit()


def get_feed_last_fetched(url):
    """Epoch seconds of the last successful fetch of this feed, or None if
    it's never been fetched — used to throttle feeds whose terms ask for
    less-frequent polling than the rest (see config.JOB_FEEDS)."""
    with get_conn() as conn:
        row = conn.execute("SELECT last_fetched_epoch FROM feed_state WHERE url=?", (url,)).fetchone()
        return row["last_fetched_epoch"] if row else None


def set_feed_last_fetched(url, epoch):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO feed_state (url, last_fetched_epoch) VALUES (?, ?) "
            "ON CONFLICT(url) DO UPDATE SET last_fetched_epoch=excluded.last_fetched_epoch",
            (url, epoch),
        )
        conn.commit()


def get_usage_stats():
    """
    Returns a summary of how people are actually using the bot — for your
    own planning, not shown to users. Keyword/region distribution tells you
    what to prioritize; nothing here is personally identifying beyond the
    chat_id count.
    """
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        active = conn.execute("SELECT COUNT(*) c FROM users WHERE active=1").fetchone()["c"]

        region_rows = conn.execute("""
            SELECT COALESCE(NULLIF(region, ''), 'both') AS region, COUNT(*) c
            FROM users GROUP BY region ORDER BY c DESC
        """).fetchall()

        keyword_rows = conn.execute(
            "SELECT keywords FROM users WHERE keywords != '' AND keywords IS NOT NULL"
        ).fetchall()

        location_rows = conn.execute("""
            SELECT COALESCE(NULLIF(location, ''), '(none)') AS location, COUNT(*) c
            FROM users GROUP BY location ORDER BY c DESC LIMIT 10
        """).fetchall()

    # Flatten comma-separated keyword lists into individual counts.
    keyword_counts = {}
    for row in keyword_rows:
        for kw in row["keywords"].split(","):
            kw = kw.strip().lower()
            if kw:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
    top_keywords = sorted(keyword_counts.items(), key=lambda x: -x[1])[:15]

    return {
        "total_users": total,
        "active_users": active,
        "paused_users": total - active,
        "region_breakdown": [(r["region"], r["c"]) for r in region_rows],
        "top_keywords": top_keywords,
        "top_locations": [(r["location"], r["c"]) for r in location_rows],
    }
