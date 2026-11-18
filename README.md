# insidejob

insidejob checks company job boards every hour and sends a Discord message when a new internship, trainee or junior role shows up.

I built it for my own summer 2027 internship search in Finland. You can point it at your own companies and keywords.

```
1 new job

RELEX Solutions – Internal Communications & Employer Branding Trainee
Helsinki, Finland · ~onsite · ~internship · https://www.relexsolutions.com/careers/jobs/?gh_jid=8014266003
```

A `~` means insidejob guessed that detail from the job text. The company didn't list it.

## How it works

1. Fetch each company's jobs from the official API or feed of their hiring system: Greenhouse, Ashby, Workday, Workable, or an RSS feed (Teamtailor, WordPress).
2. Keep the jobs whose title matches your keywords and whose location matches your places.
3. Compare them with the jobs already seen, which are saved in `seen.json`.
4. Send the new ones to Discord in one message.

A GitHub Action runs this every hour on weekdays. The list of seen jobs lives on a separate `state` branch.

Job sites like LinkedIn or Duunitori are never scraped. All data comes from public APIs that companies publish for their own job listings. [docs/sources.md](docs/sources.md) lists the sources and how each one was checked.

## Set it up

1. Fork this repo.
2. Edit [`config.yaml`](config.yaml) with your companies and keywords. [`config.example.yaml`](config.example.yaml) explains every option.
3. In Discord, open a channel's settings and go to **Integrations → Webhooks → New Webhook**. Copy the URL.
4. In your fork, go to **Settings → Secrets and variables → Actions** and add a secret named `DISCORD_WEBHOOK_URL` with that URL.
5. Create the `state` branch:
   ```sh
   git switch --orphan state
   git commit --allow-empty -m "state: initialize"
   git push origin state
   git switch main
   ```
6. Go to **Actions → Check for new jobs → Run workflow**.

The first run only saves the jobs that are already up, so you won't get a flood of old postings. After that you'll get a message whenever something new appears.

## Run it on your computer

You need [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run insidejob run --dry-run   # show matching jobs, send nothing, save nothing
uv run pytest                    # run the tests
```

For a real run, put `DISCORD_WEBHOOK_URL=...` in a `.env` file and run `uv run insidejob run`.

## How it was built

The idea, the requirements and the design decisions are mine. I wrote the code together with Claude Code, an AI coding assistant, and every pull request explains why a change was made.

## License

MIT
