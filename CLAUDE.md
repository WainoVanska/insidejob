# insidejob

Watches company career pages through official ATS APIs and RSS feeds, and alerts on new internship, trainee and junior roles (Finland first). Portfolio-quality repo: private until PR 6 works, then public.

## Working agreement
- Wäinö writes the code. Claude gives guidance, hints, small API/pattern examples and reviews. No full implementations. Short config, JSON or command snippets are fine.
- Claude does research, endpoint testing and planning, and asks before big architectural decisions (use the grilling skill for new phases).
- Each phase is a feature branch and a PR into `main`, merged by Wäinö. Claude commits only docs or this file, and only when asked.
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
- [ ] PR 1 skeleton (#3) ← next
