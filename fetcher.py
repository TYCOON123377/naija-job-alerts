"""
Fetches and parses job listings from free RSS feeds.
"""
import calendar
import logging
import re
import time

import feedparser

from config import JOB_FEEDS

logger = logging.getLogger(__name__)


def _normalize_title(title):
    """Loose normalization so 'Security Manager at Latins Security Ltd' and
    'Security Manager at Latins Security Nigeria Limited' are recognized as
    likely the same posting, without needing an exact match."""
    t = title.lower()
    t = re.sub(r"\b(limited|ltd|nigeria|plc|inc|llc)\b", "", t)
    t = re.sub(r"[^a-z0-9 ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def fetch_new_jobs():
    """
    Pulls every configured feed and returns a de-duplicated list of job dicts:
      { guid, title, link, industry, description, published, published_epoch,
        region, source_name }

    region is "nigeria" or "remote" (set per-feed in config.JOB_FEEDS), used
    downstream so users can filter to local jobs, remote/international jobs,
    or both.

    Deduplication happens on two levels:
      1. Exact guid match within a single feed (handled by the dict below).
      2. Normalized-title match ACROSS feeds — the same vacancy commonly gets
         posted to multiple boards with different guids and slightly
         different company-name formatting. First feed to report a title
         wins; later duplicates are dropped rather than alerting twice.
         (In practice this mostly catches Nigeria-board cross-posts; a
         Nigeria job and a remote job are extremely unlikely to share a
         normalized title, so this doesn't accidentally merge across regions.)

    published_epoch is a unix timestamp (UTC) when the feed gives a parseable
    date, else None — callers should treat None conservatively (see
    matcher.is_fresh).
    """
    jobs = {}
    seen_titles = set()

    for feed in JOB_FEEDS:
        feed_url = feed["url"]
        try:
            parsed = feedparser.parse(feed_url)
            if parsed.bozo and not parsed.entries:
                logger.warning("Feed failed to parse cleanly: %s", feed_url)
                continue
            for entry in parsed.entries:
                guid = entry.get("guid") or entry.get("link")
                if not guid or guid in jobs:
                    continue

                title = entry.get("title", "").strip()
                norm_title = _normalize_title(title)
                if norm_title and norm_title in seen_titles:
                    continue  # cross-feed duplicate of a job we already have

                published_epoch = None
                struct = entry.get("published_parsed")
                if struct:
                    try:
                        published_epoch = calendar.timegm(struct)
                    except (TypeError, ValueError):
                        published_epoch = None

                jobs[guid] = {
                    "guid": guid,
                    "title": title,
                    "link": entry.get("link", "").strip(),
                    "industry": entry.get("industry", "").strip() if "industry" in entry else "",
                    "description": entry.get("summary", "").strip(),
                    "published": entry.get("published", ""),
                    "published_epoch": published_epoch,
                    "region": feed["region"],
                    "source_name": feed["source_name"],
                }
                if norm_title:
                    seen_titles.add(norm_title)
        except Exception:
            logger.exception("Error fetching feed: %s", feed_url)
    return list(jobs.values())
