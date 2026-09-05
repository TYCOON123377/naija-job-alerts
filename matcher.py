"""
Matches fetched jobs against a user's saved keyword/location preferences.
"""
import time

from config import MAX_JOB_AGE_HOURS


def is_in_quiet_hours(user_row, current_hour):
    """
    user_row.quiet_start / .quiet_end are hours 0-23 (WAT) or None (no
    quiet hours set). Handles wraparound windows like 22 -> 7 (10pm-7am)
    as well as same-day windows like 9 -> 17.
    """
    start = user_row["quiet_start"]
    end = user_row["quiet_end"]
    if start is None or end is None:
        return False
    if start == end:
        return False  # a zero-length window means "off", not "always quiet"
    if start < end:
        return start <= current_hour < end
    return current_hour >= start or current_hour < end  # wraps past midnight


def is_fresh(job):
    """
    True if the job's published date is within MAX_JOB_AGE_HOURS of now.
    If the feed didn't give a parseable date, we treat it as NOT fresh —
    better to silently skip an edge case than risk alerting on something
    stale with no way to tell how stale.
    """
    epoch = job.get("published_epoch")
    if epoch is None:
        return False
    age_hours = (time.time() - epoch) / 3600
    return 0 <= age_hours <= MAX_JOB_AGE_HOURS


def job_matches_user(job, user_row):
    """
    user_row has .keywords (comma-separated string), .location (string), and
    .region ("nigeria", "remote", or "both"/empty for no filter).
    Empty keywords/location means 'match everything' for that field.
    Matching is simple case-insensitive substring matching against the
    job's title, industry, and description — good enough for an MVP.
    """
    region_pref = (user_row["region"] or "both").strip().lower()
    if region_pref not in ("both", "") and job.get("region") != region_pref:
        return False

    haystack = " ".join([
        job.get("title", ""),
        job.get("industry", ""),
        job.get("description", ""),
    ]).lower()

    keywords = (user_row["keywords"] or "").strip()
    location = (user_row["location"] or "").strip()

    if keywords:
        kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        if not any(kw in haystack for kw in kw_list):
            return False

    # Location filtering only makes sense for Nigeria-local jobs — a remote
    # role isn't tied to a Nigerian state, so a "Lagos" filter shouldn't
    # exclude a legitimately remote/worldwide posting.
    if location and location.lower() != "any" and job.get("region") != "remote":
        if location.lower() not in haystack:
            return False

    return True


def format_job_message(job):
    industry = f" ({job['industry']})" if job.get("industry") else ""
    tag = "🌍 Remote" if job.get("region") == "remote" else "🇳🇬"
    source = f" — via {job['source_name']}" if job.get("source_name") else ""
    return (
        f"{tag} <b>{job['title']}</b>{industry}{source}\n"
        f"{job['link']}"
    )


def format_digest_message(jobs, cap=15):
    """Bundles multiple matches into one message instead of flooding the
    user with a separate notification per job."""
    shown = jobs[:cap]
    lines = [f"🆕 {len(jobs)} new jobs matching your alerts:\n"]
    for j in shown:
        industry = f" ({j['industry']})" if j.get("industry") else ""
        tag = "🌍" if j.get("region") == "remote" else "🇳🇬"
        source = f" — via {j['source_name']}" if j.get("source_name") else ""
        lines.append(f"{tag} <b>{j['title']}</b>{industry}{source}\n  {j['link']}")
    if len(jobs) > cap:
        lines.append(f"\n…and {len(jobs) - cap} more this round.")
    return "\n\n".join(lines)
