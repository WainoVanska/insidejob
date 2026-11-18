# Security

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Use GitHub's private reporting instead: **Security → Report a vulnerability** on this repository. You'll get an answer within a week.

Useful things to include: what the problem is, how to reproduce it, and what an attacker could do with it.

## What's in scope

- The code in this repository and its GitHub Actions workflows.
- Anything that could leak a user's `DISCORD_WEBHOOK_URL` secret (for example into logs or alerts), let job ad content run code, or let a job title ping people in Discord.

Out of scope: the hiring systems and job feeds insidejob reads (report those to their owners), and problems in a user's own copy caused by their own changes.

## How secrets are handled

- The only secret is the Discord webhook URL. It lives in GitHub Actions secrets (or a gitignored `.env` locally), is never written to the repo, and is redacted from error messages.
- Workflows use the smallest permissions they need: `contents: read` everywhere except the hourly run, which pushes the `state` branch, and the weekly preset check, which may open an issue.
- Workflow inputs are passed through environment variables, never straight into shell commands.

## Supported versions

Only the latest `main` is supported. Copies of the template get fixes by pulling from this repository (see the README).
