"""Discord webhook notifier.

One digest per run, split into as many messages as Discord's 2,000-character limit
needs. Each job is a block, best match first:

    🟢 **RELEX** – Summer Trainee, Data Science · `10.5 / 13`
    📍 Helsinki · 🏢 ~hybrid · 💼 internship · ⏳ apply by 15.1.2027
    🔗 <https://…>
    💡 intern +3 · Helsinki +3 · data +1.5 · closes in 9 d +2

Links are wrapped in <> so Discord doesn't add a preview card for every job, and
mentions are disabled so a job title can never ping anyone.
"""

import re
import time
from collections.abc import Callable

import httpx

from insidejob.format import detail_parts, match_dot, reason_line, score_text
from insidejob.models import Job
from insidejob.rank import Rank, RankedJob

MESSAGE_LIMIT = 2000
# A single "~" is harmless (and is our "inferred" marker); "~~" would strike through.
_MARKDOWN = re.compile(r"([\\*_`|>#]|~~)")


def escape(text: str) -> str:
    """Escape Discord markdown so titles like `C++ *Intern*` render literally."""
    return _MARKDOWN.sub(lambda m: "\\~\\~" if m.group(1) == "~~" else "\\" + m.group(1), text)


def format_job(job: Job, rank: Rank | None = None) -> str:
    title = f"**{escape(job.company)}** – {escape(job.title)}"
    if rank:
        title = f"{match_dot(rank)} {title} · `{score_text(rank)}`"
    lines = [title]
    if details := detail_parts(job, icons=True, places=rank.places if rank else ()):
        lines.append(" · ".join(escape(p) for p in details))
    lines.append(f"🔗 <{job.url}>")
    if rank and rank.reasons:
        lines.append(escape(reason_line(rank, "💡 ")))
    return "\n".join(lines)


def build_messages(items: list[RankedJob], limit: int = MESSAGE_LIMIT) -> list[str]:
    """Pack job blocks into messages of at most `limit` characters, never splitting a job.

    `items` are already in the order to show (best first).
    """
    header = f"🔍 **{len(items)} new job{'s' if len(items) != 1 else ''}**"
    max_block = limit - len(header) - 2  # any single job fits with the header
    messages: list[str] = []
    current = header
    for item in items:
        block = format_job(item.job, item.rank)
        if len(block) > max_block:  # pathological title: cut it rather than fail the run
            block = block[: max_block - 1] + "…"
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
        else:
            messages.append(current)
            current = block
    if current:
        messages.append(current)
    return messages


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

    def send(self, items: list[RankedJob]) -> None:
        for i, message in enumerate(build_messages(items)):
            if i:
                self.sleep(self.pause)
            self._post(message)

    def _post(self, content: str) -> None:
        payload = {"content": content, "allowed_mentions": {"parse": []}}
        response = self.client.post(self.webhook_url, json=payload)
        if response.status_code == 429:  # rate limited: wait as told, retry once
            retry_after = float(response.json().get("retry_after", 1.0))
            self.sleep(min(retry_after, 30.0))
            response = self.client.post(self.webhook_url, json=payload)
        response.raise_for_status()
