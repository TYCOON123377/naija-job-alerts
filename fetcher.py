"""
Fetches and parses job listings from free RSS feeds.
"""
import calendar
import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

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


def fetch_new_jobs(feeds=None):
    """
    Pulls every feed in `feeds` (defaults to every configured feed) and
    returns a de-duplicated list of job dicts:
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
    if feeds is None:
        feeds = JOB_FEEDS

    jobs = {}
    seen_titles = set()

    for feed in feeds:
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


def fetch_greenhouse_jobs(boards):
    """
    Pulls each company's public Greenhouse Job Board API
    (boards-api.greenhouse.io) and returns job dicts in the same shape as
    fetch_new_jobs(), so poll_once.py can treat both lists identically.

    Each board dict is one of config.GREENHOUSE_BOARDS: {slug, region,
    source_name, remote_only}. remote_only drops any posting whose location
    doesn't contain "remote" (or does contain "hybrid") — see the comment
    above GREENHOUSE_BOARDS for why.

    Greenhouse gives each posting's last-updated time, not its original
    post date — used here as published_epoch anyway since for a job never
    seen before, "last updated" and "first posted" are the same moment in
    the overwhelming majority of cases. (An old, quietly-edited posting
    could look falsely fresh, but storage's seen-jobs tracking means that
    only matters the very first time this bot ever sees that job.)
    """
    jobs = {}
    for board in boards:
        slug = board["slug"]
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, ValueError):
            logger.exception("Error fetching Greenhouse board: %s", slug)
            continue

        for entry in data.get("jobs", []):
            location = (entry.get("location") or {}).get("name", "") or ""
            if board.get("remote_only"):
                loc_lower = location.lower()
                if "remote" not in loc_lower or "hybrid" in loc_lower:
                    continue

            guid = f"greenhouse:{slug}:{entry['id']}"

            published_epoch = None
            updated_at = entry.get("updated_at")
            if updated_at:
                try:
                    published_epoch = int(datetime.fromisoformat(updated_at).timestamp())
                except (TypeError, ValueError):
                    published_epoch = None

            description = re.sub(r"<[^>]+>", " ", entry.get("content") or "")
            description = re.sub(r"\s+", " ", description).strip()

            jobs[guid] = {
                "guid": guid,
                "title": (entry.get("title") or "").strip(),
                "link": entry.get("absolute_url", ""),
                "industry": location,
                "description": description,
                "published": updated_at or "",
                "published_epoch": published_epoch,
                "region": board["region"],
                "source_name": board["source_name"],
            }
    return list(jobs.values())
