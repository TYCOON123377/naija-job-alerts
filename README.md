# Naija Job Alerts — Telegram Bot (MVP)

Real-time job alerts for Nigeria — local AND legit remote/international
roles. Zero-spend stack: free RSS data sources, free Telegram Bot API,
free SQLite storage, free hosting via GitHub Actions.

## How it works

1. Every 15 minutes, the alerting workflow polls four confirmed-live, free
   RSS sources: MyJobMag, HotNigerianJobs (Nigeria-based), and We Work
   Remotely (remote/international — genuinely remote roles, not relocation
   listings).
2. New jobs are de-duplicated both within and **across** feeds (the same
   vacancy often gets posted to both Nigeria boards with slightly different
   company-name wording — matched and merged so you're not alerted twice).
3. Jobs posted within the last `MAX_JOB_AGE_HOURS` are matched against each
   user's saved keywords, state/location, and region preference (Nigeria
   only / remote only / both — see `/region` below).
4. Matches get pushed as a Telegram message — bundled into a single digest
   if there are more than `DIGEST_THRESHOLD` matches in one poll, so an
   active period doesn't flood anyone's chat.

No paid APIs, no scraping-ban risk (RSS is meant to be consumed), no
server cost if you host it right (see below).

## Architecture (two parts, split for cost reasons)

**1. Alerting — `poll_once.py` + GitHub Actions.** Runs once every 15
minutes via a scheduled workflow (`.github/workflows/poll.yml`), fetches
the feeds, matches, sends alerts, exits. **This costs nothing to host** —
no server, no worker dyno, no sleep/wake behavior to worry about, because
there's no always-on process at all. State (users + seen jobs + quiet-hours
queue) lives in `data/jobs.db`, which the workflow commits back to the repo
after every run.

**1b. Weekly digest — `weekly_digest.py` + GitHub Actions.** Same pattern,
runs once a week (`.github/workflows/weekly_digest.yml`). Sends a brief
"still watching" message only to users who haven't had a real alert in 7+
days — see "Weekly digest" below.

**2. Commands — `bot.py`.** Handles `/start`, `/keywords`, `/location`,
`/region`, `/quiet`, `/stats`, etc. This part genuinely does need something
running continuously, since Telegram's long-polling requires an always-on
process to receive messages. See "Free hosting for the command bot" below.

They're split deliberately: don't run the alerting loop in both places at
once, or you'll double-send every alert.

### Freshness, specifically

Two safeguards in the alerting half keep it genuinely real-time instead of
a backlog dump:

- **First-run baseline.** The very first time `poll_once.py` ever runs,
  the feed is full of jobs posted before it existed. Those get silently
  marked as "seen" with no alerts sent — otherwise the first run would
  blast every subscriber with the entire feed history. From the *second*
  run onward, only genuinely new postings trigger alerts.
- **Age cutoff.** Even after that, a job is only alerted on if its
  published date is within `MAX_JOB_AGE_HOURS` (default: 6) of right now.
  Tune this in `config.py`.

## Setup (10 minutes)

1. **Get a free bot token**
   - Open Telegram, message **@BotFather**
   - Send `/newbot`, follow the prompts, copy the token it gives you

2. **Get your own chat_id** (enables the owner-only `/stats` command)
   - Message **@userinfobot** on Telegram, it replies with your chat_id
   - Set `ADMIN_CHAT_ID` in `config.py` to that number

3. **Push this project to a GitHub repo — keep it public**
   Public repos get unlimited free GitHub Actions minutes. A private repo
   still works (2,000 free minutes/month comfortably covers a 15-minute
   schedule), but public is the safer default for staying free forever.

4. **Add your token as a repo secret**
   Repo → Settings → Secrets and variables → Actions → New repository
   secret → name it `JOB_BOT_TOKEN`, paste the token from step 1.

5. **That's it for alerting** — the workflow in `.github/workflows/poll.yml`
   picks up automatically and starts polling on its schedule. Trigger a
   manual run from the Actions tab if you don't want to wait 15 minutes.

6. **For the command bot** (`/start`, `/keywords`, etc.), see the hosting
   options below, then locally:
   ```bash
   pip install -r requirements.txt
   export JOB_BOT_TOKEN="123456:ABC-your-token-here"
   python bot.py
   ```

7. Open Telegram, find your bot by the username you gave it, send `/start`.

8. **Before telling anyone else about it**, work through `TESTING.md` —
   a live end-to-end checklist. Everything here is unit-tested in
   isolation, but it hasn't run against real Telegram servers yet.

## Bot commands (for users)

- `/start` — register
- `/help` — list all commands
- `/keywords developer, sales, remote` — set what jobs to match (comma-separated)
- `/categories` — pick keywords from tappable buttons instead of typing
- `/location Lagos` — set a state filter, or `/location any` for everywhere
  (only applies to Nigeria-region jobs — remote jobs aren't state-bound)
- `/region nigeria` — Nigeria-based jobs only
- `/region remote` — remote/international jobs only (We Work Remotely)
- `/region both` — everything (default)
- `/quiet 22 7` — hold alerts from 10pm-7am WAT, delivered as one digest
  when the window ends; `/quiet off` to disable
- `/status` — see your current settings
- `/pause` / `/resume` — stop/start alerts without losing your settings
- `/deleteme confirm` — permanently erase your data (not just pause)

## Owner tools

- **`/stats`** — usage breakdown (total/active/paused users, region split,
  top keywords, top locations) sent only to whoever's chat_id matches
  `ADMIN_CHAT_ID` in `config.py`. Silent no-op for everyone else — it
  doesn't even reveal the command exists to non-owners.
- **Uptime monitoring.** Since the command bot uses long-polling (no
  exposed port), a normal HTTP health-check doesn't apply. Instead it
  supports a free "dead man's switch": set `HEALTHCHECK_PING_URL` (from a
  free healthchecks.io account) and the bot pings it every
  `HEALTHCHECK_PING_INTERVAL_MINUTES`. If the process dies or hangs, the
  pings stop and healthchecks.io alerts you — instead of finding out when
  a subscriber complains. Needs `pip install 'python-telegram-bot[job-queue]'`
  to actually schedule the ping (falls back to a warning if that's missing).
- **`LAUNCH_MESSAGE.md`** — ready-to-paste pitch text for sharing the bot
  (short version, long version, thread version) once you're ready.
- **`TESTING.md`** — a live end-to-end checklist to work through before
  sharing this with anyone. Do this before `LAUNCH_MESSAGE.md`, not after.

## Quiet hours

`/quiet 22 7` holds matches found between 10pm and 7am WAT instead of
sending them immediately — nobody wants a job alert waking them up. Held
jobs queue in the `pending_alerts` table and get delivered as a single
digest the moment the next poll runs *after* quiet hours end, even if that
poll itself found zero new jobs on its own (the queued ones still get
flushed). Wraparound windows (e.g. 22→7, crossing midnight) and same-day
windows (e.g. 9→17) both work — see `matcher.is_in_quiet_hours` if you want
to verify the boundary logic yourself.

## Weekly digest

Silence from a bot is indistinguishable from a bot that's broken.
`weekly_digest.py`, run once a week via its own GitHub Actions workflow,
sends a short "still watching, nothing matched this week" message — but
**only** to users who haven't received a real alert in the last 7 days.
Someone getting daily alerts doesn't need filler; someone whose keywords
are narrow enough that nothing's matched in a week benefits from knowing
it's still working rather than wondering if it died. Tracked via
`last_notified_at`, stamped every time a real alert successfully sends.

## Account deletion

`/deleteme confirm` removes a user's row entirely — not a pause, an actual
erasure of their keywords, location, and preferences. Requires the
`confirm` argument specifically so it can't be triggered accidentally;
`/deleteme` alone just shows the warning. Relevant both as general good
practice and for Nigeria's NDPR (data protection regulation), which gives
users a right to erasure.

## Free hosting for the command bot

The alerting half needs no hosting at all (see Architecture above) — this
section is only about where `bot.py` runs to answer `/keywords` etc.
**Correction from earlier advice:** Railway's ongoing free tier is gone
(now a one-time $5 trial credit) and Render's Background Workers now start
at $7/month — neither is actually free anymore as of 2026. Genuinely free
options for this specific piece:

- **Oracle Cloud "Always Free" tier** — a real always-on micro VM, free
  indefinitely (not a trial), no card charged unless you explicitly
  upgrade. The most durable free option here; slightly more setup (SSH in,
  run `bot.py` under a process manager like `systemd` or `tmux`).
- **A spare always-on device you already have** — an old phone with
  Termux, a Raspberry Pi, a PC that's on anyway. Zero marginal cost.
- **Render's free Web Service tier** (not Background Worker) — free tier
  services sleep after inactivity and take ~1 minute to wake on the next
  request. Workable for a low-traffic command bot if you switch it to
  **webhook mode** instead of `run_polling()`, since a webhook just needs
  to respond when Telegram calls it, not stay awake polling in a loop.
  This requires a small code change from what's here — ask if you want it.

Set `JOB_BOT_TOKEN` as an environment variable wherever you run it — never
commit it to code (the GitHub Actions secret from setup step 4 is separate
from this and doesn't need to match how you expose it here).

## Extending this

- **More sources**: add entries to `JOB_FEEDS` in `config.py` — each needs
  a `url`, `region` ("nigeria" or "remote"), and `source_name` for
  attribution. Cross-feed duplicate detection is automatic within a region.
  **Before adding a source, check its terms of use** — this is why
  Remotive isn't included despite being an obvious candidate (see comment
  in `config.py`). Not every "public RSS feed" is free to redistribute to
  a subscriber list; read the terms, not just whether the URL resolves.
- **Smarter location matching**: right now location matching is a simple
  substring check against the job title/description text. HotNigerianJobs
  states the location explicitly in its description (e.g. "Abuja (FCT)"),
  which makes this noticeably more reliable than MyJobMag's summarized feed
  alone — worth leaning on it more if location precision matters most.
- **Android app**: once this validates real demand (people actually using
  `/keywords` and staying subscribed), the same fetch/match logic can move
  behind a proper backend (Supabase/Firebase) with push notifications for
  a Watchman-style Android app.

## On competing with LinkedIn, Indeed, Jobberman

Worth being honest about this rather than overselling it: a solo,
zero-budget MVP will never out-scale LinkedIn or Indeed on raw listing
volume — they have direct employer relationships, paid job-posting
revenue, and years of data this can't match. Trying to "win" on breadth is
a losing game.

The actual openings, based on what those platforms are structurally bad
at for this specific audience:

- **Speed.** LinkedIn/Indeed/Jobberman are all *pull* — you open the app
  and search. This is *push* — a match lands in Telegram the moment it's
  posted, no daily habit required. For the small number of jobs that get
  100+ applicants in the first hour, being first matters more than being
  thorough.
- **Zero cost, zero data burden.** No ads, no "upgrade to see who viewed
  your profile," and Telegram is already something most Nigerian users
  have installed and use on minimal data — unlike loading LinkedIn's full
  web app repeatedly on a limited data bundle.
- **One inbox for local + remote-dollar income**, instead of checking
  Jobberman for local roles and a separate remote-job site for
  international ones. That combination is the actual differentiator — not
  matching either platform's scale, but being the thing neither of them
  is: unified, free, and push-based for *this* audience specifically.
- **Where this genuinely can't compete**: employer-side features (posting,
  applicant tracking, recruiter search), professional networking, company
  research, and sheer catalog size. Don't try to build those — that's
  LinkedIn's actual business, not a job-alert bot's.

The realistic path to "beating" them isn't feature parity — it's being
meaningfully better at the one job this does (fast, free, relevant
alerts) for people currently underserved by apps built for higher-bandwidth,
ad-tolerant markets.

## Effectiveness notes (free-tier specific)

- **Digest mode** (`DIGEST_THRESHOLD` in `config.py`) keeps a high-volume
  poll from flooding one user with 10+ separate messages — it also keeps
  you comfortably under Telegram's flood-control limits.
- **Cross-feed dedup** means adding a third or fourth free source later is
  low-risk — coverage grows without duplicate spam, as long as titles are
  reasonably similar across boards (loose normalization, not exact match).
- **Auto-pause on blocked/deleted chats.** If a user blocks the bot or
  deletes their account, sending to them fails identically forever —
  without handling this, every future poll would retry and log an
  "error" for someone who simply left. `poll_once.py` distinguishes this
  (Telegram's `Forbidden`/`BadRequest`) from real transient failures and
  auto-pauses only the former, so logs stay meaningful and cycles aren't
  wasted retrying a permanently dead send target.
- **Offset cron minute.** The workflow runs at `:04/:19/:34/:49` rather
  than the exact quarter-hour — GitHub's scheduler deprioritizes runs that
  land on the most common boundaries (`:00/:15/:30/:45`) under platform
  load, so offsetting avoids silently dropped or delayed runs.
- **The committed-DB approach is simple but not infinitely scalable.** Fine
  for hundreds of users; if `data/jobs.db` starts causing merge conflicts
  or the repo bloats, that's the signal to move state to a free external
  DB (Supabase's free Postgres tier) instead of committing it to git.

## Known limitations (MVP, by design)

- Four data sources for now (MyJobMag, HotNigerianJobs, We Work Remotely).
  Good combined coverage across local + remote, but not exhaustive.
- Matching is keyword substring — no fuzzy matching or ranking yet.
- The command bot (`bot.py`) still needs *something* always-on, even though
  alerting doesn't — see "Free hosting for the command bot" above.
- Remotive deliberately excluded — their terms prohibit exactly this use
  case (see `config.py` comment).
