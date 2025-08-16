import asyncio

from app.worker.pipeline import Pipeline, Topic, AdminBotClient
from app.common.utils import count_tokens, calculate_cost


class FakeLLMClient:
    provider = "openai"
    model = "gpt-3.5-turbo"

    def __init__(self, response: str = "summary") -> None:
        self.response = response

    def complete(self, prompt: str, **kwargs: object) -> str:
        return self.response


def test_split_topics_limit() -> None:
    llm = FakeLLMClient()
    pipeline = Pipeline(llm, AdminBotClient())
    raw = "Topic1\n\nTopic2\n\nTopic3\n\nTopic4"
    post = pipeline.parse(raw)
    topics = pipeline.split_topics(post)
    assert len(topics) == 3


def test_assemble_digest_limit() -> None:
    llm = FakeLLMClient()
    pipeline = Pipeline(llm, AdminBotClient())
    topics = [Topic(id=i, text="t", links=[], summary=str(i)) for i in range(1, 15)]
    digest, remaining = pipeline.assemble_digest(topics)
    assert len(digest) == 10
    assert len(remaining) == 4


def test_summarize_records_cost() -> None:
    llm = FakeLLMClient("short summary")
    pipeline = Pipeline(llm, AdminBotClient())
    topic = Topic(id=1, text="hello world", links=[])
    pipeline.summarize(topic)
    tokens_in = count_tokens("hello world")
    tokens_out = count_tokens("short summary")
    rate_prompt = 0.001
    rate_completion = 0.002
    expected = int(round((calculate_cost(tokens_in, rate_prompt) + calculate_cost(tokens_out, rate_completion)) * 100))
    assert topic.tokens_in == tokens_in
    assert topic.tokens_out == tokens_out
    assert topic.cost_cents == expected


def test_expand_links_concurrency() -> None:
    llm = FakeLLMClient()
    pipeline = Pipeline(llm, AdminBotClient())
    topics = [Topic(id=1, text="", links=["u1", "u2", "u3"])]
    in_flight = 0
    max_in_flight = 0

    async def fake_fetch(url: str) -> str:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return url

    pipeline.expand_links(topics, concurrency=2, fetch_func=fake_fetch)
    assert max_in_flight <= 2
    assert topics[0].expanded_links == {"u1": "u1", "u2": "u2", "u3": "u3"}


def test_moderate_uses_admin_bot() -> None:
    llm = FakeLLMClient()
    admin = AdminBotClient(approve=False)
    pipeline = Pipeline(llm, admin)
    topic = Topic(id=1, text="t", links=[])
    pipeline.moderate(topic)
    assert topic.approved is False
