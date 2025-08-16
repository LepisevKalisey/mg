from __future__ import annotations

"""Minimal processing pipeline used in tests."""

from typing import List

from .common.llm_client import LLMError
from .common.utils import extract_links, split_topics


class Pipeline:
    """Tiny synchronous pipeline used for integration/E2E tests."""

    def __init__(self, llm, telethon_client, log_sink: List[str]):
        self.llm = llm
        self.telethon = telethon_client
        self.log_sink = log_sink

    def process_post(self, text: str) -> List[str]:
        """Process ``text`` and return list of summaries.

        Each topic is summarised via the provided LLM client and sent to the
        moderation channel through the Telethon client. Summaries are stored in
        ``log_sink`` representing the published digest. Errors from the LLM are
        caught and converted into placeholder summaries.
        """

        summaries: List[str] = []
        for topic in split_topics(text):
            _ = extract_links(topic)  # exercise link parser
            try:
                summary = self.llm.complete(topic)
            except LLMError:
                summary = f"ERROR: {topic[:20]}"
            self.telethon.send_message("moderation", summary)
            self.log_sink.append(summary)
            summaries.append(summary)
        return summaries
