from app.pipeline import Pipeline


class StubLLM:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"stub:{prompt}"


class TelethonMock:
    def __init__(self):
        self.sent = []

    def send_message(self, channel: str, text: str) -> None:
        self.sent.append((channel, text))


def test_pipeline_integration():
    llm = StubLLM()
    tele = TelethonMock()
    sink: list[str] = []
    pipeline = Pipeline(llm, tele, sink)

    result = pipeline.process_post("Topic one\n\nTopic two")

    assert llm.prompts == ["Topic one", "Topic two"]
    assert tele.sent == [
        ("moderation", "stub:Topic one"),
        ("moderation", "stub:Topic two"),
    ]
    assert sink == result == ["stub:Topic one", "stub:Topic two"]
