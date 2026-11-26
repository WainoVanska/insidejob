# Contributing

The most useful thing is suggesting a company: open an issue with the **Suggest a company** form.

For code: `uv sync`, make the change with tests, then run `uv run ruff format`, `uv run ruff check` and `uv run pytest` before opening a PR into `main`. Say why in the PR, not just what.

A few rules: official job APIs and feeds only (no scraping, no job boards like LinkedIn), no working around bot protection, and nothing personal or secret in the repo. New preset companies need their endpoint and terms checked in [`docs/sources.md`](docs/sources.md).
