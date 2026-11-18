# Contributing

Thanks for helping! The easiest and most useful contribution is **suggesting a company** for a preset: open an issue with the **Suggest a company / preset** form.

## Ground rules

These keep insidejob polite and legal for everyone who runs it. Pull requests that break them can't be merged.

- **Official APIs and feeds only.** insidejob reads the public job APIs and RSS/JSON feeds that hiring systems publish (Greenhouse, Ashby, Workable, Teamtailor, WordPress feeds). No HTML scraping, and never job boards like LinkedIn, Duunitori, Oikotie or Jobly.
- **Don't work around bot protection.** If a site blocks automated requests (Workday blocks GitHub Actions, for example), it stays out.
- **Be polite.** Sequential requests with a pause, one request per company per run where possible, and the descriptive User-Agent from `pipeline.py`.
- **No secrets and nothing personal** in the repository: no webhooks, tokens, CVs, or anyone's own company list and preferences.
- Check new ideas against the **Scope** section of [CLAUDE.md](CLAUDE.md): insidejob is a watchlist of companies, not a job board.

## Adding a company to a preset

1. Find the company's hiring system: open a job ad on its careers page and look at the link (see the list in `config.example.yaml`).
2. **Test the endpoint** with a plain request, for example
   `curl -s https://boards-api.greenhouse.io/v1/boards/<board>/jobs | head`
   or run `uv run insidejob check` with the link in a test `config.yaml`. It must answer without logging in.
3. **Check the terms and `robots.txt`** of the host you'd request, and record what you found in [`docs/sources.md`](docs/sources.md): the system, identifier, endpoint, the date you tested it, and anything unusual.
4. Add the link to `presets/<name>.yaml` as `"Company: <link>"`, in the section for its hiring system.
5. Run `uv run insidejob presets` to check every preset board still answers.

## Code changes

1. Fork, then create a branch from `main`.
2. Install [uv](https://docs.astral.sh/uv/) and run `uv sync`.
3. Make the change with tests. Tests never touch the network: adapters have a pure `parse()` tested on saved fixtures in `tests/fixtures/`.
4. Before pushing:
   ```sh
   uv run ruff format
   uv run ruff check
   uv run pytest
   ```
5. Open a pull request into `main`. Explain **why** in the description, not only what: a reviewer should be able to defend every line.

New hiring systems (adapters) are welcome when they have an official public API or feed. Each adapter is a module in `src/insidejob/adapters/` with `fetch()` (HTTP) and `parse()` (pure), registered in `adapters/__init__.py`; see the existing ones.
