from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import urllib.request
try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover - yaml might be missing at runtime
    yaml = None  # type: ignore

from app.common.llm_client import LLMClient, LLMError
from app.common.utils import calculate_cost, count_tokens


@dataclass
class Topic:
    """Container for an individual topic extracted from a post."""

    id: int
    text: str
    links: List[str]
    expanded_links: Dict[str, str] = field(default_factory=dict)
    summary: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_cents: int = 0
    approved: bool = False


class AdminBotClient:
    """Very small stub representing an admin bot.

    Real implementation would interact with Telegram; here we only simulate
    approvals by returning a preset decision.
    """

    def __init__(self, approve: bool = True) -> None:
        self.approve = approve

    def send_moderation_card(self, topic: Topic) -> bool:
        return self.approve


class Pipeline:
    """Processing pipeline for digest generation."""

    def __init__(
        self,
        llm_client: LLMClient,
        admin_bot: AdminBotClient,
        prices_path: str = "config/prices.yaml",
        *,
        error_threshold: int = 5,
        cool_down_seconds: int = 60,
    ) -> None:
        self.llm = llm_client
        self.admin_bot = admin_bot
        with open(prices_path, "r", encoding="utf-8") as fh:
            text = fh.read()
            if yaml:
                self.prices = yaml.safe_load(text) or {}
            else:  # very small YAML subset parser
                self.prices = self._parse_prices(text)
        self.error_threshold = error_threshold
        self.cool_down_seconds = cool_down_seconds
        self._error_count = 0
        self._circuit_open_until = 0.0

    def _parse_prices(self, text: str) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Parse a tiny subset of YAML used for price files.

        Supports structures like::

            provider:
              model:
                prompt: 0.001
                completion: 0.002
        """

        data: Dict[str, Dict[str, Dict[str, float]]] = {}
        provider: Optional[str] = None
        model: Optional[str] = None
        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            if not raw.startswith(" "):
                provider = raw.rstrip(":")
                data[provider] = {}
            elif raw.startswith("  ") and not raw.startswith("    "):
                model = raw.strip().rstrip(":")
                data[provider][model] = {}
            else:
                key, val = raw.strip().split(":", 1)
                data[provider][model][key.strip()] = float(val.strip())
        return data

    # ---- stages -----------------------------------------------------
    def parse(self, raw: str) -> Dict[str, List[str] | str]:
        """Parse raw text and extract links."""
        links = re.findall(r"https?://\S+", raw)
        return {"text": raw, "links": links}

    def split_topics(self, post: Dict[str, List[str] | str]) -> List[Topic]:
        """Split post text into topics, up to three per post."""
        chunks = [c.strip() for c in re.split(r"\n\s*\n", str(post["text"])) if c.strip()]
        topics: List[Topic] = []
        for idx, chunk in enumerate(chunks[:3], start=1):
            links = re.findall(r"https?://\S+", chunk)
            topics.append(Topic(id=idx, text=chunk, links=links))
        return topics

    def expand_links(
        self,
        topics: List[Topic],
        *,
        concurrency: int = 5,
        fetch_func: Optional[Callable[[str], "asyncio.Future[str]"]] = None,
    ) -> None:
        """Fetch link contents concurrently with a limit."""

        async def _default_fetch(url: str) -> str:
            def _fetch() -> str:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    return resp.read().decode("utf-8")

            return await asyncio.to_thread(_fetch)

        fetch_func = fetch_func or _default_fetch

        async def _run() -> None:
            sem = asyncio.Semaphore(concurrency)

            async def _expand(topic: Topic) -> None:
                results: Dict[str, str] = {}

                async def _fetch(url: str) -> None:
                    async with sem:
                        results[url] = await fetch_func(url)

                await asyncio.gather(*(_fetch(u) for u in topic.links))
                topic.expanded_links = results

            await asyncio.gather(*(_expand(t) for t in topics))

        asyncio.run(_run())

    def _check_circuit(self) -> None:
        if time.time() < self._circuit_open_until:
            raise LLMError("circuit breaker open")

    def _record_success(self) -> None:
        self._error_count = 0

    def _record_failure(self) -> None:
        self._error_count += 1
        if self._error_count >= self.error_threshold:
            self._circuit_open_until = time.time() + self.cool_down_seconds
            self._error_count = 0

    def summarize(self, topic: Topic) -> None:
        """Summarize a topic using the LLM and record usage stats."""
        self._check_circuit()
        prompt = topic.text
        for url, content in topic.expanded_links.items():
            prompt += f"\nSource: {url}\n{content}\n"
        tokens_in = count_tokens(prompt)
        try:
            result = self.llm.complete(prompt)
        except LLMError:
            self._record_failure()
            raise
        self._record_success()
        tokens_out = count_tokens(result)
        provider = self.llm.provider
        model = self.llm.model
        rate_prompt = float(self.prices[provider][model]["prompt"])
        rate_completion = float(self.prices[provider][model]["completion"])
        cost = calculate_cost(tokens_in, rate_prompt) + calculate_cost(
            tokens_out, rate_completion
        )
        topic.summary = result
        topic.tokens_in = tokens_in
        topic.tokens_out = tokens_out
        topic.cost_cents = int(round(cost * 100))

    def moderate(self, topic: Topic) -> None:
        """Send moderation card and store approval."""
        topic.approved = self.admin_bot.send_moderation_card(topic)

    def assemble_digest(self, topics: List[Topic]) -> tuple[List[Topic], List[Topic]]:
        """Return (digest_topics, remaining_topics) respecting max 10 topics."""
        digest = topics[:10]
        remaining = topics[10:]
        return digest, remaining

    def publish(self, topics: List[Topic]) -> str:
        """Combine topics into a digest string ready for posting."""
        lines = [f"- {t.summary}" for t in topics]
        return "\n".join(lines)


__all__ = ["Pipeline", "Topic", "AdminBotClient"]
