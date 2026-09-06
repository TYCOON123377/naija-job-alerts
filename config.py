"""
Config and constants for Naija Job Alerts bot.
"""
import os

# Set this as an environment variable, never hardcode it.
# Get a free token from @BotFather on Telegram.
BOT_TOKEN = os.environ.get("JOB_BOT_TOKEN", "")

# How often to poll the job feeds, in minutes.
POLL_INTERVAL_MINUTES = 15

# A job older than this is never alerted on, even if the bot has never seen
# it before (guards against feed backfills / reordered entries surfacing
# stale postings as "new").
MAX_JOB_AGE_HOURS = 6

# If a single poll produces more matches than this for one user, send them
# as one digest message instead of one message each — keeps things from
# feeling spammy and stays well under Telegram's per-chat flood limits.
DIGEST_THRESHOLD = 4

# Seconds to wait between individual Telegram sends. Telegram's real limit
# is roughly 30 messages/second globally and ~1/second per chat; this is
# deliberately conservative since we're on a free/shared IP.
SEND_DELAY_SECONDS = 0.05

# Free, live, real-time RSS feeds. MyJobMag confirmed working as of testing.
# Add more free feeds here as you validate them (e.g. HotNigerianJobs, if its
# feed is confirmed live too).
JOB_FEEDS = [
    {
        "url": "https://www.myjobmag.com/feeds/ng/jobsxml.xml",
        "region": "nigeria",
        "source_name": "MyJobMag",
    },
    {
        "url": "https://www.myjobmag.com/feeds/ng/jobsxml_by_categories.xml",
        "region": "nigeria",
        "source_name": "MyJobMag",
    },
    {
        "url": "https://www.hotnigerianjobs.com/feed/rss.xml",
        "region": "nigeria",
        "source_name": "HotNigerianJobs",
    },
    {
        "url": "https://weworkremotely.com/remote-jobs.rss",
        "region": "remote",
        "source_name": "We Work Remotely",
    },
    {
        "url": "https://www.jobzilla.ng/feed",
        "region": "nigeria",
        "source_name": "Jobzilla",
    },
    {
        # Jobicy's terms explicitly allow this kind of use if we keep
        # attribution and the original job link (both already true — see
        # matcher.format_job_message), but their feed's own legal notice
        # asks integrators to poll "a few times daily", not every 15
        # minutes like the rest of these feeds. min_interval_minutes below
        # is what makes poll_once.py respect that (see storage.feed_state).
        "url": "https://jobicy.com/?feed=job_feed",
        "region": "remote",
        "source_name": "Jobicy",
        "min_interval_minutes": 240,
    },
    # Deliberately NOT including Remotive or Himalayas: both feeds' terms
    # explicitly prohibit resubmitting their jobs to third-party platforms
    # (Remotive names LinkedIn Jobs; Himalayas names Jooble/Neuvoo/Google
    # Jobs/LinkedIn Jobs as examples) — which is exactly what this bot
    # does. Respect the terms, skip the source, rather than build on
    # borrowed time.
]

# Companies whose public Greenhouse job board we pull directly — this is
# Greenhouse's own documented public Job Board API (boards-api.greenhouse.io),
# not scraping, so it carries none of the redistribution-terms risk the RSS
# aggregators above do. Greenhouse doesn't publish a numeric rate limit but
# asks integrators not to hammer it, hence min_interval_minutes here too.
#
# remote_only=True drops onsite/hybrid postings for companies whose board
# mixes both, so region="remote" means the same thing it does for the RSS
# feeds above (genuinely remote, not hybrid) rather than "this company has
# a remote policy somewhere on their board."
GREENHOUSE_BOARDS = [
    {
        "slug": "moniepoint",
        "region": "nigeria",
        "source_name": "Moniepoint",
        "remote_only": False,
        "min_interval_minutes": 120,
    },
    {
        "slug": "gitlab",
        "region": "remote",
        "source_name": "GitLab",
        "remote_only": True,
        "min_interval_minutes": 120,
    },
    {
        "slug": "stripe",
        "region": "remote",
        "source_name": "Stripe",
        "remote_only": True,
        "min_interval_minutes": 120,
    },
    {
        "slug": "webflow",
        "region": "remote",
        "source_name": "Webflow",
        "remote_only": True,
        "min_interval_minutes": 120,
    },
    # Checked and skipped: Flutterwave, Paystack, Andela, Kuda, Interswitch,
    # PalmPay, OPay (none run Greenhouse or Lever — no public API found);
    # Figma (Greenhouse board has zero remote-only listings, nothing to add).
]

NIGERIAN_STATES = [
    "Abia", "Abuja", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa",
    "Benue", "Borno", "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti",
    "Enugu", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi",
    "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun",
    "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
    "Remote",
]

# Overridable so the Vercel-hosted command bot can point this at /tmp
# (its filesystem is read-only everywhere else) while poll_once.py, running
# on GitHub Actions, keeps using the checked-out repo path.
DB_PATH = os.environ.get("JOBS_DB_PATH") or os.path.join(os.path.dirname(__file__), "data", "jobs.db")

# Owner-only command — set this to your own Telegram chat_id so /stats
# doesn't leak usage numbers to every subscriber. Find your chat_id by
# messaging @userinfobot on Telegram. Leave as None to disable /stats.
ADMIN_CHAT_ID = None  # e.g. 123456789

# Optional: a healthchecks.io "ping URL" for dead-man's-switch monitoring
# of the always-on command bot (see README → "Uptime monitoring").
# Free tier, no card required. Leave blank to disable.
HEALTHCHECK_PING_URL = os.environ.get("HEALTHCHECK_PING_URL", "")
HEALTHCHECK_PING_INTERVAL_MINUTES = 10

# Preset keyword bundles for the /categories inline-button flow — lowers
# the barrier for users who don't want to type exact keyword syntax.
CATEGORY_KEYWORDS = {
    "tech": ("💻 Tech / IT", "developer, software, IT, engineer, programmer, data"),
    "sales": ("📈 Sales / Marketing", "sales, marketing, business development, digital marketing"),
    "admin": ("🗂️ Admin / Office", "admin, secretary, office assistant, executive assistant"),
    "customer_service": ("☎️ Customer Service", "customer service, customer support, call center"),
    "finance": ("💰 Finance / Accounting", "accounting, finance, audit, bookkeeping, accountant"),
    "healthcare": ("🏥 Healthcare", "nurse, medical, healthcare, pharmacist, hospital"),
    "education": ("📚 Education", "teacher, education, lecturer, tutor, school"),
    "engineering": ("🔧 Engineering", "engineer, engineering, technical, mechanical, civil"),
}
