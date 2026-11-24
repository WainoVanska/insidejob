"""Discord webhook notifier.

One digest per run, split into as many messages as Discord's 2,000-character limit
needs. Each job is two lines:

    **RELEX** – Summer Trainee, Data Science
    Helsinki · ~hybrid · internship · apply by 15.1.2027 · <https://…>

Links are wrapped in <> so Discord doesn't add a preview card for every job, and
mentions are disabled so a job title can never ping anyone.
"""

import re
import time
from collections.abc import Callable
from datetime import date

import httpx

from insidejob.format import detail_parts
from insidejob.models import Job

MESSAGE_LIMIT = 2000
# A single "~" is harmless (and is our "inferred" marker); "~~" would strike through.
_MARKDOWN = re.compile(r"([\\*_`|>#]|~~)")


def escape(text: str) -> str:
    """Escape Discord markdown so titles like `C++ *Intern*` render literally."""
    return _MARKDOWN.sub(lambda m: "\\~\\~" if m.group(1) == "~~" else "\\" + m.group(1), text)


def format_job(job: Job) -> str:
    details = " · ".join([*(escape(p) for p in detail_parts(job)), f"<{job.url}>"])
    return f"**{escape(job.company)}** – {escape(job.title)}\n{details}"


def build_messages(jobs: list[Job], limit: int = MESSAGE_LIMIT) -> list[str]:
    """Pack job blocks into messages of at most `limit` characters, never splitting a job."""
    header = f"**{len(jobs)} new job{'s' if len(jobs) != 1 else ''}**"
    max_block = limit - len(header) - 2  # any single job fits with the header
    messages: list[str] = []
    current = header
    for job in jobs:
        block = format_job(job)
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


def build_heartbeat(boards: int, matching: int, failing: list[tuple[str, date]]) -> str:
    """The weekly "still alive" message.

    `failing` is (board key, failing since) for each board that failed this run.
    """
    lines = [
        "**insidejob weekly check-in**",
        f"{boards} boards checked · {len(failing)} failed · {matching} matching jobs open",
    ]
    for key, since in failing:
        lines.append(f"⚠ {escape(key)} failing since {since.day}.{since.month}.")
    return "\n".join(lines)


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

    def send(self, jobs: list[Job]) -> None:
        for i, message in enumerate(build_messages(jobs)):
            if i:
                self.sleep(self.pause)
            self._post(message)

    def send_text(self, content: str) -> None:
        self._post(content[:MESSAGE_LIMIT])

    def _post(self, content: str) -> None:
        payload = {"content": content, "allowed_mentions": {"parse": []}}
        response = self.client.post(self.webhook_url, json=payload)
        if response.status_code == 429:  # rate limited: wait as told, retry once
            retry_after = float(response.json().get("retry_after", 1.0))
            self.sleep(min(retry_after, 30.0))
            response = self.client.post(self.webhook_url, json=payload)
        response.raise_for_status()
