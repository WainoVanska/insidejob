# insidejob

Watches company career pages through official ATS APIs and RSS feeds, and alerts on new internship, trainee and junior roles (Finland first). Portfolio-quality repo: private until PR 6 works, then public.

## Working agreement
- Since 2026-11-18 (PR 2 onwards), Claude implements the issues: code, tests, commits and PRs. PR descriptions explain the reasoning so Wäinö can review and defend every line.
- Wäinö makes the decisions, reviews and merges every PR, and does the account-bound steps (Discord webhook, GitHub Secrets, making the repo public).
- Claude does research, endpoint testing and planning, and asks before big architectural decisions or anything that changes the agreed design (use the grilling skill for new phases).
- Each issue is a feature branch and a PR into `main` with `Closes #N`.
- Keep this file updated with decisions, sources and status.

## Hard rules
- No HTML scraping of job boards (LinkedIn, Duunitori, Oikotie, Jobly…). Official ATS APIs and RSS/JSON feeds only. Later: Gmail API on own inbox, by label.
- Check terms/robots per source and record the result in `docs/sources.md`.
- Polite: sequential requests, short pause, descriptive User-Agent (repo URL, no personal email).
- No secrets in the repo (GitHub Secrets / gitignored `.env`).

## Agreed design (grilling session 2026-11-18)

**Tooling:** Python >= 3.11, uv (`uv.lock`), pytest, ruff (check + format in CI), MIT license. Runtime deps: `httpx`, `PyYAML`, and stdlib `xml.etree` for RSS (not feedparser, which drops Teamtailor's `tt:` namespace). No pydantic.

**Package:** `src/insidejob/`, entry point `insidejob = "insidejob.cli:main"` (also `python -m insidejob`). CLI: `insidejob run [--dry-run] [--config PATH] [--state PATH]`. `--dry-run` fetches, filters and prints, with no alerts and no state write.

**Job model:** `id` (`source:board:job_id`), company, title, location (one string, multiple locations joined with `"; "`), url, `posted_at: datetime | None`, workplace (onsite/hybrid/remote), employment (full-time/part-time/internship/fixed-term), start, deadline. The last four are optional and each records whether it was *listed* by the source or *inferred*. The description is kept in memory only, never in state.

**Pipeline:** fetch → parse → enrich → filter → diff → notify → save.
- Fetch: sequential, one shared `httpx.Client`, ~20 s timeout, short pause between requests. Descriptions are fetched: Greenhouse `?content=true`, Ashby `descriptionPlain`, RSS `description`.
- Adapters keep `fetch` (HTTP) separate from `parse(raw) -> list[Job]` (pure, fixture-tested). Adapters fill in only what the source lists.
- `enrich.py` uses regex heuristics (EN + FI) on title and description to fill missing workplace, employment and start, marked as inferred. No signal means the field is left unknown.
- Filters: title include regex + title exclude regex (`senior|lead|principal|staff|director|manager|head of`) + location include. Set globally in `config.yaml`; a company-level list **replaces** the global one. Workplace, employment, start and deadline are display only in v1.
- Config is loaded into dataclasses with hand-written validation (unknown type, missing board, invalid regex), failing fast with a clear message.

**State:** `seen.json` = `{ "<source>:<board>": { "<job_id>": {"first_seen": ISO, "last_seen": ISO} } }`.
- A job is new only if its ID hasn't been seen before (edits don't re-alert; reposts with a new ID do).
- A board key that doesn't exist yet means seed silently, with no alerts.
- IDs missing for 60 days are pruned.
- A failed source is skipped and its state is left untouched. The run continues and exits non-zero at the end.

**Alerts:** Discord webhook first (`DISCORD_WEBHOOK_URL` secret), behind a `Notifier` interface so Telegram can be added later. One digest per run; nothing is sent when there's nothing new. Split at 2,000 characters. Plain text, two lines per job, with unknown fields left out and inferred values marked with `~`:
```
**RELEX** – Summer Trainee, Data Science
Helsinki · hybrid · internship · start ~Jun 2027 · apply by 15.1.2027 · <https://…>
```

**Automation:** GitHub Actions cron `0 4-18 * * 1-5` (UTC, about 06–20 Finnish time, weekdays) + `workflow_dispatch`. `concurrency` group so runs never overlap. State lives on an orphan `state` branch, checked out into `state/` and committed as `github-actions[bot]` only when it changed (`permissions: contents: write`). CI runs ruff + pytest on every PR. Tests never touch the network.

**Logging:** stdlib `logging`, one INFO line per source (`greenhouse:relex fetched=35 matched=2 new=1`), failures at ERROR.

**Config:** the real `config.yaml` is committed (no secrets), plus `config.example.yaml`.

## PR plan
Tracked on GitHub as milestones (Phase 1–4) and issues. Each PR references its issue with `Closes #N`. Labels: `research`, `adapter`, `pipeline`, `infra`, `alerts`, `documentation`, `needs-design` (grill before building).

1. Skeleton: pyproject, uv, ruff, pytest, CI workflow, LICENSE, .gitignore
2. `Job` model + Greenhouse adapter + fixture tests
3. Config loading + filters
4. State + enrich + pipeline + `--dry-run`
5. Discord notifier
6. Scheduled Action + `state` branch, then make the repo public
7. RSS adapter (Teamtailor `tt:` extras; also covers Gofore and Rovio WordPress feeds)
8. Ashby adapter
9. README with setup guide and example config

## Deferred (Phase 3+)
- Match score from a `profile.yaml` (or LinkedIn data export, not login): a "7/10 requirements met" checklist, likely LLM-based. Needs its own grilling round.
- Workday adapter (NVIDIA, KONE), Workable (Varjo, Nitor), Oracle (Nokia), Eightfold (Ericsson).
- Filtering on workplace/employment, Telegram notifier, Gmail alert source, Aiven Greenhouse token.

## Sources
See `docs/sources.md` (verified 2026-11-18). Greenhouse 9, Teamtailor RSS 5, WordPress RSS 2, Ashby 3, Workable 2, Workday 2, Oracle 1, Eightfold 1, no clean source 5.

## Status
- [x] Phase 1: source research → `docs/sources.md`
- [x] Design agreed (above)
- [x] PR 1 skeleton (#3), merged as #21
- [x] v1 live (2026-11-18): #4–#8 merged via #27, Discord alerts confirmed, actions bumped (#28), README (#29)
- [x] More adapters merged (#30–#33): RSS (#9), Ashby (#10), Workday (#12), Workable (#13)
- [x] Workday disabled in `config.yaml`: Cloudflare 429s GitHub Actions runners. 21 active companies
- [x] Weekly heartbeat (feat/weekly-heartbeat): Monday 05:30 UTC run with `--heartbeat` posts a summary; per-board health in `health.json` on the `state` branch (`last_ok`, `failing_since`). Chosen weekly over daily: a daily ping becomes noise you stop reading.
- [ ] Wäinö: make the repo public
- Later / needs design: Oracle (#14), Eightfold (#15), Aiven token (#16), field filters (#18), match score (#19), Gmail (#20). Telegram (#17) parked: not wanted for now.

## Implementation notes (v1)
- The state diff runs on **all** fetched jobs, not only matches: loosening a filter never alerts on old postings. Order per source: fetch → parse → state diff → filter → enrich.
- State stores dates, not timestamps, so `seen.json` changes at most once a day per job and the Action doesn't commit every hour.
- Prune only boards fetched OK this run; empty boards are kept (otherwise a board with 0 jobs would re-seed silently later).
- Alert before saving state: if Discord fails, state isn't saved and the jobs are retried next run.
- Exit codes: 0 ok, 1 a source or the alert failed, 2 bad config/state or no webhook.
- `--dry-run` prints every matching job tagged seed/NEW/seen, so filters can be checked on a fresh state.
- Jobs with an empty location pass the location filter.

## Adapter notes
- Each adapter: `fetch(client, board, options)` (HTTP) + pure `parse(raw, board, company)`; optional `OPTIONS = {name: required}` validated by config. Register in `adapters/__init__.py`.
- `board` doubles as the state key, so keep it stable: rss/workday use the URL without `https://`.
- Ashby and Workable *list* workplace/employment (not inferred). ICEYE marks interns `FullTime`: we keep what the source says.
- Teamtailor `remoteStatus`: fully/hybrid/none → remote/hybrid/onsite.
- WordPress feeds only show the newest ~10 posts: fine for new-job alerts.
- Workday: undocumented API, page size max 20, offsets past the end repeat results. `facet` option narrows server-side; ~2–3 requests per board per run. **Blocked from GitHub Actions**: Cloudflare returns 429 to runner IPs on the first request (home IP gets 200), so it's disabled in `config.yaml` and only usable locally. Don't work around bot protection.
