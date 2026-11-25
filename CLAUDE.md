# insidejob

Watches company career pages through official ATS APIs and RSS feeds, and alerts on new internship, trainee and junior roles. Public template: anyone forks or copies it and puts their own companies and preferences in `config.yaml`.

## Working on this repo
- Each change is a feature branch and a PR into `main`. The PR description explains *why*, so a reviewer can defend every line.
- Ask before big architectural decisions or anything that changes the design below.
- Keep this file updated with decisions. Nothing personal goes into the public repo: a user's companies, ranking taste and job history live in their own copy's `config.yaml` and `state` branch.

## Hard rules
- No HTML scraping of job boards (LinkedIn, Duunitori, Oikotie, Jobly…). Official ATS APIs and RSS/JSON feeds only.
- Check terms/robots per source and record the result in `docs/sources.md`.
- Polite: sequential requests, short pause, descriptive User-Agent (repo URL, no personal email).
- Don't work around bot protection (see Workday below).
- No secrets in the repo (GitHub Secrets / gitignored `.env`).

## Scope
What insidejob is for. Check new ideas against this before building them.
1. Straight from companies' own hiring systems, hourly (often jobs that never reach job boards).
2. A watchlist of companies you'd love to work at, not a keyword search: low noise.
3. Ranked for you, with the reasons (🟢🟡🔴, score, 💡 points).
4. In Discord: one digest per run, 🆕 on new jobs, Top N on demand.
5. Free and open source, no account, ads or tracking; preferences and job history stay in the user's own copy.
6. Early-career focus (intern, thesis, junior, graduate; seniors filtered, experience asks penalised). Kept subtle in the README.

Don't build: all-jobs feeds (Duunitori, Työmarkkinatori), a hosted website or accounts, HTML scraping, CV storage or parsing in code (the README's "Let AI fill it in" prompt runs in the user's own AI chat), a non-junior focus.

**Setup target:** from "Use this template" to a welcome message in Discord in about 5 minutes, in the browser only: no installs, no git commands, no regex.

## Design

**Tooling:** Python >= 3.11, uv (`uv.lock`), pytest, ruff (check + format in CI), MIT license. Runtime deps: `httpx`, `PyYAML`, and stdlib `xml.etree` for RSS (not feedparser, which drops Teamtailor's `tt:` namespace). No pydantic.

**Package:** `src/insidejob/`, entry point `insidejob = "insidejob.cli:main"` (also `python -m insidejob`).
- `insidejob run [--dry-run] [--config PATH] [--state PATH]`: the hourly alert. `--dry-run` fetches, filters and prints, with no alerts and no state write.
- `insidejob top [--count N] [--dry-run]`: sends the N best-matching current jobs, new or not. Reads state only to mark jobs first seen in the last 7 days with 🆕; never saves it.
- `insidejob presets [--report PATH]`: maintenance, fetches every preset board once, exit 1 if any fail.
- `insidejob check [--config PATH]`: validates the config, fetches every board with an empty in-memory state and shows the companies, match counts and the top 5 with scores (terminal, plus `$GITHUB_STEP_SUMMARY` and `::error::` annotations in Actions). Never sends, never needs the webhook; exits 1 on a config error or a board that can't be read.

**Job model:** `id` (`source:board:job_id`), company, title, location (one string, multiple locations joined with `"; "`), url, `posted_at: datetime | None`, workplace (onsite/hybrid/remote), employment (full-time/part-time/internship/fixed-term), start, deadline. The last four are optional and each records whether it was *listed* by the source or *inferred*. The description is kept in memory only, never in state.

**Pipeline:** fetch → parse → state diff → filter → enrich → rank → notify → save.
- Fetch: sequential, one shared `httpx.Client`, ~20 s timeout, short pause between requests. Descriptions are fetched: Greenhouse `?content=true`, Ashby `descriptionPlain`, RSS `description`.
- Adapters keep `fetch` (HTTP) separate from `parse(raw) -> list[Job]` (pure, fixture-tested). Adapters fill in only what the source lists.
- `enrich.py` uses regex heuristics (EN + FI) on title and description to fill missing workplace, employment and start, marked as inferred. No signal means the field is left unknown.
- Filters: title include regex + title exclude regex + location include. Generated from `looking_for` or set globally under `filters:`; a company-level key **replaces** the global one.
- Config is loaded into dataclasses with hand-written validation, failing fast with a clear message.

**Ranking** (`rank.py`): a points score with a "why" line whose reasons add up to the score. `DEFAULT_RANK` is **neutral** so it fits anyone: title level (intern 3 / junior 2 / graduate 1), deadline (≤14 d +2, ≤30 d +1), and −2 if the text asks for 2+ years of experience. Users add location, interests and start date through `looking_for` (or exact rules under `rank:`). Rules match with `words: [...]` (whole words, any case, no regex needed) or `match: '<regex>'`. `title_only: true` ignores the description (for words like "AI" that company boilerplate repeats in nearly every ad: counting mentions was tried and didn't separate real AI jobs from marketing). Colours are relative: `levels: {green: 0.65, yellow: 0.4}` = share of the best score possible (`max_score`), so they still fit when rules change.

**State:** `seen.json` = `{ "<source>:<board>": { "<job_id>": {"first_seen": ISO date, "last_seen": ISO date} } }`.
- A job is new only if its ID hasn't been seen before (edits don't re-alert; reposts with a new ID do).
- A board key that doesn't exist yet means seed silently, with no alerts.
- IDs missing for 60 days are pruned.
- A failed source is skipped and its state is left untouched. The run continues and exits non-zero at the end.

**Alerts:** Discord webhook (`DISCORD_WEBHOOK_URL` secret), behind a `Notifier` interface. One digest per run; nothing is sent when there's nothing new. Each job is an **embed** (card), best match first, at most 10 embeds / ~6,000 embed characters per message. Header: `🆕 N new jobs` for `run` (🆕 before every title) or `🏆 Top N jobs right now` for `top`. The left bar and dot show the match level (🟢/🟡/🔴), the score is shown out of the best possible, and each 💡 reason shows its points. Unknown fields are left out, inferred values marked with `~`, and at most 3 locations are shown, most relevant first:
```
┃ ICEYE                                   (author)
┃ 🆕 ICEYE Engineering Intern Lab 2027    (title, links to the job)
┃ 🟢 9.5 / 13
┃ 📍 Espoo, Finland · 🏢 hybrid · 💼 full-time · 🗓️ ~starts May 2027 · ⏳ apply by 15.1.2027
┃ 💡 intern +3 · Espoo +3 · computer vision +1.5 · summer 2027 +2
```

**Automation:** `run.yml`: cron `0 4-18 * * 1-5` (UTC, weekdays) + `workflow_dispatch`, `concurrency` group so runs never overlap. A `setup` job skips everything when `DISCORD_WEBHOOK_URL` isn't set, so a fresh copy doesn't fail hourly. State lives on an orphan `state` branch, checked out into `state/` as a git worktree and committed as `github-actions[bot]` only when it changed; the first run creates the branch, so users never run git. `top.yml`: manual only, `count` choice (3/5/10/25), `contents: read`, never pushes, works before the state branch exists. `check.yml`: `insidejob check` on pushes to `config.yaml`/`presets/**` and on demand, `contents: read`, no secrets. `ci.yml`: ruff + pytest on every PR. `sync.yml` (copies only, not this repo): weekly, merges upstream `main` into `sync/upstream` via `.github/scripts/sync-upstream.sh` and opens a PR. `config.yaml` and `CLAUDE.local.md` always keep the copy's version; any other conflict opens an issue instead. Template copies share no history, so their first sync takes upstream for everything else (`-X theirs`). Needs a `SYNC_TOKEN` PAT (contents, PRs, issues, workflows): `GITHUB_TOKEN` can't push workflow changes; without it the job skips with a notice. Tests never touch the network.

**Welcome message:** the first real run (state has no boards yet) seeds silently as always, then sends "✅ insidejob is set up! Watching N companies · M matching jobs right now. New ones arrive here marked 🆕." with the top 3. If that send fails: log it, still save state (the seeding worked), exit 1.

**Logging:** stdlib `logging`, one INFO line per source (`greenhouse:relex fetched=35 matched=2 new=1`), failures at ERROR.

**Config:** `config.yaml` is a small working starter (`looking_for` with placeholder values + `companies` as links); `config.example.yaml` documents every option: looking_for and companies on top, advanced `filters:`/`rank:` below (tests load its `rank` as `EXAMPLE_RANK`, so it must stay valid).
- `looking_for:` (`profile.py`) turns plain words into filters and rank parts, in the same YAML shape a hand-written config uses, so normal validation checks the result. `roles` intern/thesis/junior/graduate (default all; title points 3/3/2/1; the senior exclude is always on). `cities` +3, `country` +2 (alias map: Finland also matches Suomi), `remote` +1 (`true` = EU/Europe/EMEA/Nordics pass the filter, `anywhere` = any remote job). `unknown_location`: 2 with a country, 1 with only cities, else 0. `interests`: built-in synonym groups, unknown words used as written, 3 in the title / half in the description; boilerplate words (AI, data, cloud, agile, digital, innovation, automation, analytics, platform, sustainability, design) become a separate `title_only` rule. `start`: a season or month (optional year) → EN + FI regex, +2. Explicit `filters:`/`rank:` keys replace generated ones key by key.
- `companies:` (`links.py`): a job or board link, `Name: link`, or a full `{company, type, board, options, filters}` entry. Links are parsed offline (Greenhouse, Ashby, Workable, Teamtailor, `.rss` and `/feed/` URLs); Workday and unknown sites get a plain-words error. `sources:` still works and is combined. The same board twice is merged silently, first entry wins.
- Presets: `- preset: fi-software` expands `presets/<name>.yaml` (a `companies:` list in the same forms; no nested presets). A `presets/` folder next to the config wins over the repo's. Only verified boards go in (live endpoint + terms/robots in `docs/sources.md`), never Workday. Board strings must stay identical to hand-written entries so switching to a preset never re-seeds. `insidejob presets` pings every preset board; `presets.yml` runs it weekly (main repo only) and opens or comments on an issue when one fails.

## Implementation notes
- The state diff runs on **all** fetched jobs, not only matches: loosening a filter never alerts on old postings.
- State stores dates, not timestamps, so `seen.json` changes at most once a day per job and the Action doesn't commit every hour.
- Prune only boards fetched OK this run; empty boards are kept (otherwise a board with 0 jobs would re-seed silently later).
- Alert before saving state: if Discord fails, state isn't saved and the jobs are retried next run.
- Exit codes: 0 ok, 1 a source or the alert failed, 2 bad config/state or no webhook.
- `--dry-run` prints every matching job tagged seed/NEW/seen, so filters can be checked on a fresh state.
- Jobs with an empty location pass the location filter.
- Weekly heartbeat: Monday 05:30 UTC cron runs `run --heartbeat`, which posts a check-in after saving state (header + one red card per failing board). Board health lives in `health.json` next to `seen.json` (`last_ok`, `failing_since`; dates only), separate so the state format is unchanged. Weekly, not daily: a daily ping becomes noise.

## Adapter notes
- Each adapter: `fetch(client, board, options)` (HTTP) + pure `parse(raw, board, company)`; optional `OPTIONS = {name: required}` validated by config. Register in `adapters/__init__.py`.
- `board` doubles as the state key, so keep it stable: rss/workday use the URL without `https://`.
- Ashby and Workable *list* workplace/employment (not inferred); we keep what the source says, even when it looks wrong.
- Teamtailor `remoteStatus`: fully/hybrid/none → remote/hybrid/onsite.
- WordPress feeds only show the newest ~10 posts: fine for new-job alerts.
- Workday: undocumented API, page size max 20, offsets past the end repeat results. `facet` option narrows server-side; ~2–3 requests per board per run. **Blocked from GitHub Actions**: Cloudflare returns 429 to runner IPs on the first request, so it's only usable locally.

## Ideas, not built
- A "does this fit me" score from the user's profile (requirements checklist, likely LLM-based).
- Oracle and Eightfold adapters, Telegram notifier, Gmail alert source, filtering on workplace/employment.
- `insidejob find <careers page URL>`: detect the hiring system from a careers page (job links are already parsed offline by `links.py`).
