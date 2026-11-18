# insidejob

[![CI](https://github.com/WainoVanska/insidejob/actions/workflows/ci.yml/badge.svg)](https://github.com/WainoVanska/insidejob/actions/workflows/ci.yml)

Follow the companies you'd love to work at. insidejob checks their hiring systems every hour and posts new internships and junior jobs to your Discord, ranked for you, with the reasons.

Free, open source, no account. Set up in 5 minutes.

![A Discord alert from insidejob](docs/discord-alert.png)

## Setup

You need a GitHub account and a Discord server.

1. Click **Use this template → Create a new repository**. Private is fine.
2. In Discord, open your channel's settings → **Integrations → Webhooks → New Webhook** and copy its URL. In your new repo, go to **Settings → Secrets and variables → Actions**, add a secret called `DISCORD_WEBHOOK_URL` and paste the URL.
3. Edit [`config.yaml`](config.yaml) on GitHub: say what you're looking for and which companies to watch (keep the `fi-software` preset, paste job links, or both). Commit. **Actions → Check config** then shows what matches.
4. Go to **Actions → Check for new jobs → Run workflow**. Discord gets a welcome message with your best matches, then new jobs every hour on weekdays.

For the best jobs open right now, run **Actions → Top jobs**.

## Let AI fill it in

Paste this and your CV into any AI chat, then copy the answer into `config.yaml`. Your CV stays in that chat.

```text
From my CV below, write a YAML block for my job alert tool. Use exactly this shape and
only these keys, and answer with the YAML only:

looking_for:
  roles: [intern, thesis, junior, graduate]   # keep only the ones that fit me
  cities: [...]                                # where I live or want to work
  country: ...                                 # e.g. Finland
  remote: true                                 # true, false, or anywhere
  interests: [...]                             # 3-6 short words, e.g. graphics, AI, games,
                                               # web, data, design, marketing, or a technology
  start: ...                                   # e.g. summer 2027, or leave the line out

My CV:
<paste your CV here>
```

Every option is explained in [`config.example.yaml`](config.example.yaml). Prefer to fork instead of using the template? That works too, but forks are public.

## How it was built

The idea, the requirements and the design decisions are mine. I wrote the code with Claude Code, an AI coding assistant, and every pull request explains why a change was made.

## License

MIT
