# 🔍 insidejob

Checks company job boards every hour and posts new internship, trainee and junior roles to Discord, best matches first.

I built it for my own summer 2027 internship search in Finland.

**It isn't a scraper.** It only reads the official job APIs and feeds that companies publish for their own listings, about one request per company per hour. Job sites like LinkedIn are never touched. [docs/sources.md](docs/sources.md) shows how each source was checked.

![A Discord alert from insidejob](docs/discord-alert.png)

## How it works

1. Fetch each company's jobs from the official API or feed of its hiring system (Greenhouse, Ashby, Workable, Teamtailor and WordPress RSS).
2. Keep jobs whose title and location match `config.yaml`.
3. Skip jobs already seen, then rank the new ones with a simple points score (title, city, interests, start date, deadline).
4. Send them to Discord in one message, marked 🆕. A GitHub Action does this hourly on weekdays.

Want the best jobs open right now, new or not? Run **Actions → Top jobs** and pick 3, 5, 10 or 25.

## Set it up

1. Fork the repo and edit [`config.yaml`](config.yaml) ([`config.example.yaml`](config.example.yaml) explains every option).
2. Create a Discord webhook (channel settings → **Integrations → Webhooks**) and save its URL as the Actions secret `DISCORD_WEBHOOK_URL`.
3. Create an empty `state` branch, where the seen jobs are stored:
   ```sh
   git switch --orphan state && git commit --allow-empty -m "state: init" && git push origin state && git switch main
   ```
4. Run **Actions → Check for new jobs → Run workflow**. The first run only records current jobs; after that you get a message whenever something new appears.

To try it locally with [uv](https://docs.astral.sh/uv/): `uv sync`, then `uv run insidejob run --dry-run` (prints matches, sends and saves nothing).

## How it was built

The idea, the requirements and the design decisions are mine. I wrote the code together with Claude Code, an AI coding assistant, and every pull request explains why a change was made.

## License

MIT
