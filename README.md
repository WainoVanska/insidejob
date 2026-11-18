# 🔍 insidejob

Watches the job boards of the companies you'd like to work for and posts new internship, trainee and junior roles to Discord, best matches first.

**It isn't a scraper.** It only reads the official job APIs and feeds that companies publish for their own listings, about one request per company per hour. Job sites like LinkedIn are never touched. [docs/sources.md](docs/sources.md) shows how each source was checked.

![A Discord alert from insidejob](docs/discord-alert.png)

## How it works

1. Fetch each company's jobs from the official API or feed of its hiring system (Greenhouse, Ashby, Workable, Teamtailor and WordPress RSS).
2. Keep jobs whose title and location match your `config.yaml`.
3. Skip jobs already seen, then rank the new ones with a simple points score: how junior the title is, the deadline, and optionally your cities, interests and start date.
4. Send them to Discord in one message, marked 🆕. A GitHub Action does this hourly on weekdays.

Want the best jobs open right now, new or not? Run **Actions → Top jobs** and pick 3, 5, 10 or 25.

## Use it yourself

1. **Fork** this repo (public; updates with one click), or click **Use this template → Create a new repository** for a private copy.
2. Edit [`config.yaml`](config.yaml): list your companies and adjust the filters. To find a company's board, open its careers page and look at where the job links go:

   | Link looks like | Config line |
   |---|---|
   | `job-boards.greenhouse.io/acme` | `{ company: Acme, type: greenhouse, board: acme }` |
   | `jobs.ashbyhq.com/acme` | `{ company: Acme, type: ashby, board: acme }` |
   | `apply.workable.com/acme` | `{ company: Acme, type: workable, board: acme }` |
   | `acme.teamtailor.com/jobs` | `{ company: Acme, type: rss, board: acme.teamtailor.com/jobs.rss }` |

   For ranking by your cities, interests and start date, copy the `rank:` section from [`config.example.yaml`](config.example.yaml), which explains every option.
3. Create a Discord webhook (channel settings → **Integrations → Webhooks**) and save its URL as the Actions secret `DISCORD_WEBHOOK_URL`.
4. Create an empty `state` branch, where the seen jobs are stored:
   ```sh
   git switch --orphan state && git commit --allow-empty -m "state: init" && git push origin state && git switch main
   ```
5. Run **Actions → Check for new jobs → Run workflow**. The first run only records the jobs already up, so you aren't flooded with old postings. After that you get a message whenever something new appears.

Check your filters before going live with [uv](https://docs.astral.sh/uv/): `uv sync`, then `uv run insidejob run --dry-run` prints every matching job with its score and sends nothing.

Getting later improvements: a fork has a **Sync fork** button on GitHub. A template copy starts with its own history, so the first update needs one extra flag (keep your `config.yaml` if Git asks):
```sh
git remote add upstream https://github.com/WainoVanska/insidejob.git
git pull upstream main --allow-unrelated-histories
```

## How it was built

The idea, the requirements and the design decisions are mine. I wrote the code together with Claude Code, an AI coding assistant, and every pull request explains why a change was made.

## License

MIT
