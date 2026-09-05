# Live test checklist

Everything in this project is unit-tested in isolation, but it has not yet
run against real Telegram servers or been through a full live cycle. Work
through this before sharing the bot with anyone else — it'll surface things
tests can't catch (a malformed HTML entity from a feed breaking
`parse_mode="HTML"`, a Telegram API quirk, a GitHub Actions permissions
issue).

## 1. Get credentials

- [ ] Message @BotFather on Telegram, `/newbot`, save the token
- [ ] Message @userinfobot to get your own chat_id
- [ ] Set `ADMIN_CHAT_ID` in `config.py` to your chat_id (enables `/stats`)

## 2. Local smoke test (before touching GitHub Actions)

- [ ] `pip install -r requirements.txt`
- [ ] `export JOB_BOT_TOKEN="..."`
- [ ] `python bot.py` — watch the console for startup errors
- [ ] In Telegram, message your bot: `/start` — confirm you get the welcome text
- [ ] `/help` — confirm all commands listed
- [ ] `/keywords developer, remote` — confirm confirmation message
- [ ] `/categories` — confirm 8 buttons render; tap one, confirm keywords
  update AND the message edits in place (not a new message)
- [ ] `/location Lagos` — confirm it's accepted
- [ ] `/location Wakanda` — confirm it's rejected with a helpful message
- [ ] `/region remote` — confirm confirmation message
- [ ] `/region blah` — confirm it's rejected with the valid options listed
- [ ] `/quiet 22 7` — confirm confirmation message with the times shown
- [ ] `/quiet 5` (only one number) — confirm it's rejected with usage help
- [ ] `/quiet 25 3` (out of range) — confirm it's rejected
- [ ] `/quiet off` — confirm it's accepted
- [ ] `/status` — confirm it shows everything you just set correctly,
  including quiet hours (or "off")
- [ ] `/pause` then `/status` — confirm it shows paused
- [ ] `/resume` then `/status` — confirm it shows active again
- [ ] `/stats` — confirm you (as admin) get the usage breakdown
- [ ] `/deleteme` (no args) — confirm you get the warning, NOT deletion
- [ ] `/deleteme confirm` — confirm you get the deletion message, then
  `/status` — confirm it now says "not registered" (send `/start` again
  afterward so the rest of this checklist still has a user to test with)
- [ ] Stop `bot.py` (Ctrl+C) — confirm it exits cleanly

## 3. First live poll (the part most likely to surface real bugs)

- [ ] `python poll_once.py` — run it manually, once, locally
- [ ] Check the console output: does it say "First run — baselined N jobs"?
  If not on a fresh `data/jobs.db`, something's wrong with the baseline logic.
- [ ] Delete `data/jobs.db` if you want a clean baseline test, or leave it —
  either way, confirm no alerts were sent on this first run (check Telegram)
- [ ] Run `python poll_once.py` a **second** time a few minutes later
- [ ] If any genuinely new jobs matched your `/keywords`, confirm you
  actually received them in Telegram, correctly formatted:
  - [ ] HTML renders correctly (bold title, no visible `<b>` tags, no
    broken entities from special characters in a job title)
  - [ ] The 🇳🇬 vs 🌍 tag matches the job's actual source
  - [ ] The "via [Source]" attribution is present and correct
  - [ ] The link actually opens the right job posting
- [ ] If you got 5+ matches in one run, confirm it arrived as ONE digest
  message, not five separate ones

## 4. GitHub Actions deployment

- [ ] Push the repo to GitHub — **public**, for free unlimited Actions minutes
- [ ] Repo → Settings → Secrets and variables → Actions → add `JOB_BOT_TOKEN`
  (used by both `poll.yml` and `weekly_digest.yml` — one secret, two workflows)
- [ ] Actions tab → find "poll-job-feeds" → "Run workflow" (manual trigger,
  don't wait for the schedule)
- [ ] Watch the run: does it succeed? Check the logs for the same
  baseline/fresh-job messages you saw locally
- [ ] Check the repo: did `data/jobs.db` get committed back with a
  "[skip ci]" commit message?
- [ ] Wait for (or trigger again after) the next real interval — confirm a
  **second** automated run doesn't re-baseline or re-send anything already sent

## 5. Edge cases worth deliberately triggering

- [ ] Set `/keywords` to something with zero current matches (e.g. a very
  specific, unlikely term) — confirm you get NO alerts (not everything)
- [ ] Set `/keywords` to something broad (e.g. "manager") — confirm you DO
  get alerts and they're relevant
- [ ] Set `/region nigeria` then check a run — confirm no 🌍 remote jobs
  arrive even if they'd match your keywords
- [ ] Set `/region remote` with `/location Lagos` — confirm remote jobs
  still arrive (location shouldn't block remote-region jobs — see
  matcher.py comment)
- [ ] Block the bot in Telegram (from your own account or a test account),
  trigger a poll that would've matched you, then check `data/jobs.db` /
  `/stats` — confirm you were auto-paused rather than the poll silently
  failing forever on your chat_id

## 6. Quiet hours

- [ ] `/quiet <current_hour+1> <current_hour+2>` — set a window that
  covers the next couple of hours so you're "in quiet hours" right now
- [ ] Trigger `python poll_once.py` manually with something that should
  match your keywords — confirm you get NO message
- [ ] Check `data/jobs.db`'s `pending_alerts` table (or just trust the
  logs — should say "Queued N match(es)...") — confirm the match was queued
- [ ] `/quiet off` (moves you out of the quiet window)
- [ ] Trigger `poll_once.py` again, even with zero *new* jobs this time —
  confirm the previously-queued match(es) now arrive as a digest
- [ ] Confirm `pending_alerts` is empty for your chat_id after that delivery

## 7. Weekly digest

- [ ] `python weekly_digest.py` locally, manually — for a freshly-`/start`ed
  account (never notified), confirm you receive the "still watching" message
- [ ] Trigger a real match via `poll_once.py` first (so `last_notified_at`
  is recent), then run `weekly_digest.py` again — confirm you do NOT get
  a second, redundant message
- [ ] On GitHub: Actions tab → "weekly-still-here-digest" → "Run workflow"
  manually — confirm it succeeds and commits `data/jobs.db` back, same as
  the main poll workflow

## 8. If you enabled heartbeat monitoring

- [ ] Sign up free at healthchecks.io, create a check, copy the ping URL
- [ ] `export HEALTHCHECK_PING_URL="https://hc-ping.com/your-uuid"`
- [ ] Restart `bot.py`, wait ~10 minutes, confirm the healthchecks.io
  dashboard shows a recent successful ping
- [ ] Stop `bot.py` deliberately, confirm healthchecks.io eventually flags
  it as down (this is the whole point — confirm the alarm actually fires)

## Only after all of this: share the bot

Use `LAUNCH_MESSAGE.md` once the above is clean. Don't skip straight to
sharing — an MVP that misfires on day one (double alerts, broken
formatting, missed matches) is much harder to recover trust from than one
that launches a day later but works.
