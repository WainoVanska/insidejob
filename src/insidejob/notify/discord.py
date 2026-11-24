"""Discord webhook notifier.

One digest per run. Each job is an embed (a card) whose left bar is coloured by match
level, best match first:

    ┃ RELEX                                     (author: the company)
    ┃ 🆕 Summer Trainee, Data Science           (title: links to the job; 🆕 if fresh)
    ┃ 🟢 10.5 / 13
    ┃ 📍 Helsinki · 🏢 ~hybrid · 💼 internship · ⏳ apply by 15.1.2027
    ┃ 💡 intern +3 · Helsinki +3 · data +1.5 · closes in 9 d +2

A message holds at most 10 embeds and 6,000 embed characters, so a busy run is split
into several messages; the first one carries the header: "🆕 N new jobs" for the hourly
alert, or "🏆 Top N jobs right now" for `insidejob top`. Mentions are disabled so a job
title can never ping anyone.
"""

import re
import time
from collections.abc import Callable
from datetime import date

import httpx

from insidejob.format import detail_parts, fi_date, match_dot, plural, reason_line, score_text
from insidejob.models import Job
from insidejob.rank import Rank, RankedJob

EMBEDS_PER_MESSAGE = 10
EMBED_CHARS_PER_MESSAGE = 5500  # Discord allows 6,000; leave room for how it counts emoji
TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096

COLOURS = {3: 0x2ECC71, 2: 0xF1C40F, 1: 0xE74C3C}  # green, yellow, red
NO_RANK_COLOUR = 0x99AAB5  # Discord grey
NEW_MARK = "🆕"

# A single "~" is harmless (and is our "inferred" marker); "~~" would strike through.
_MARKDOWN = re.compile(r"([\\*_`|>#]|~~)")


def escape(text: str) -> str:
    """Escape Discord markdown so text like `C++ *Intern*` renders literally."""
    return _MARKDOWN.sub(lambda m: "\\~\\~" if m.group(1) == "~~" else "\\" + m.group(1), text)


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def job_embed(job: Job, rank: Rank | None = None, *, fresh: bool = False) -> dict:
    """One job as a Discord embed. Titles are plain text in embeds, so only the
    description (which renders markdown) is escaped. `fresh` puts 🆕 before the title."""
    lines = []
    if rank:
        lines.append(f"**{match_dot(rank)} {score_text(rank)}**")
    if details := detail_parts(job, icons=True, places=rank.places if rank else ()):
        lines.append(" · ".join(escape(p) for p in details))
    if rank and rank.reasons:
        lines.append(escape(reason_line(rank, "💡 ")))
    embed = {
        "author": {"name": _cut(job.company, TITLE_LIMIT)},
        "title": _cut(f"{NEW_MARK} {job.title}" if fresh else job.title, TITLE_LIMIT),
        "url": job.url,
        "color": COLOURS.get(rank.stars, COLOURS[1]) if rank else NO_RANK_COLOUR,
    }
    if lines:
        embed["description"] = _cut("\n".join(lines), DESCRIPTION_LIMIT)
    return embed


def embed_size(embed: dict) -> int:
    """Characters Discord counts towards the per-message embed limit."""
    return (
        len(embed.get("title", ""))
        + len(embed.get("description", ""))
        + len(embed.get("author", {}).get("name", ""))
    )


def new_jobs_header(count: int) -> str:
    return f"{NEW_MARK} **{count} new job{'s' if count != 1 else ''}**"


def top_header(count: int) -> str:
    return f"🏆 **Top {count} job{'s' if count != 1 else ''} right now**"


def welcome_header(companies: int, matching: int, shown: int) -> str:
    """The first run's message: proof that the setup works, before any new job appears."""
    text = (
        f"✅ **insidejob is set up!** Watching {plural(companies, 'company', 'companies')}"
        f" · {plural(matching, 'matching job')} right now."
        f" New ones arrive here marked {NEW_MARK}."
    )
    if shown:
        text += f"\nThe best {plural(shown, 'match', 'matches')} open now:"
    return text


def build_payloads(items: list[RankedJob], header: str | None = None) -> list[dict]:
    """Pack job embeds into as few webhook messages as Discord's limits allow.

    `items` are already in the order to show (best first). Jobs are never split.
    The first message carries `header` (default: "🆕 N new jobs").
    """
    batches: list[list[dict]] = [[]]
    size = 0
    for item in items:
        embed = job_embed(item.job, item.rank, fresh=item.fresh)
        full = len(batches[-1]) >= EMBEDS_PER_MESSAGE
        if batches[-1] and (full or size + embed_size(embed) > EMBED_CHARS_PER_MESSAGE):
            batches.append([])
            size = 0
        batches[-1].append(embed)
        size += embed_size(embed)

    payloads = [{"embeds": batch, "allowed_mentions": {"parse": []}} for batch in batches]
    payloads[0]["content"] = header or new_jobs_header(len(items))
    return payloads


HEARTBEAT_MARK = "🩺"
FAILING_COLOUR = COLOURS[1]  # red, like a weak match: something needs a look


def heartbeat_payload(companies: int, matching: int, failing: list[tuple[str, str, date]]) -> dict:
    """The weekly check-in, in the same style as the job alerts: an emoji header line,
    then one red card per failing board (company as author, like a job card).

    `failing` is (company, board key, failing since) for each board that failed this run.
    """
    header = (
        f"{HEARTBEAT_MARK} **Weekly check-in** · {plural(companies, 'company', 'companies')}"
        f" checked · {plural(matching, 'matching job')} open"
    )
    if failing:
        header += f" · ⚠️ {plural(len(failing), 'board')} failing"
    else:
        header += " · all boards OK"
    embeds = [
        {
            "author": {"name": _cut(company, TITLE_LIMIT)},
            "title": f"⚠️ Failing since {fi_date(since)}",
            "description": escape(key),
            "color": FAILING_COLOUR,
        }
        for company, key, since in failing[:EMBEDS_PER_MESSAGE]
    ]
    payload: dict = {"content": header, "allowed_mentions": {"parse": []}}
    if embeds:
        payload["embeds"] = embeds
    return payload


class DiscordNotifier:
    def __init__(
        self,
        webhook_url: str,
        client: httpx.Client,
        *,
        pause: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.webhook_url = webhook_url
        self.client = client
        self.pause = pause
        self.sleep = sleep

    def send(self, items: list[RankedJob], header: str | None = None) -> None:
        for i, payload in enumerate(build_payloads(items, header)):
            if i:
                self.sleep(self.pause)
            self.post(payload)

    def post(self, payload: dict) -> None:
        response = self.client.post(self.webhook_url, json=payload)
        if response.status_code == 429:  # rate limited: wait as told, retry once
            retry_after = float(response.json().get("retry_after", 1.0))
            self.sleep(min(retry_after, 30.0))
            response = self.client.post(self.webhook_url, json=payload)
        response.raise_for_status()
