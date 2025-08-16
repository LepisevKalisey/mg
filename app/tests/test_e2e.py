import pytest

try:
    from alembic import command
    from alembic.config import Config
    ALEMBIC_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - environment missing alembic
    ALEMBIC_AVAILABLE = False

from app.common.errors import LLMError
from app.pipeline import Pipeline


class FailingLLM:
    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise LLMError("boom")
        return f"ok:{prompt}"


class TelethonMock:
    def __init__(self):
        self.sent = []

    def send_message(self, channel: str, text: str) -> None:
        self.sent.append((channel, text))


@pytest.mark.e2e
def test_e2e(tmp_path):
    if not ALEMBIC_AVAILABLE:
        pytest.skip("alembic not installed")

    db_path = tmp_path / "e2e.db"
    db_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    llm = FailingLLM()
    tele = TelethonMock()
    sink: list[str] = []
    pipeline = Pipeline(llm, tele, sink)

    pipeline.process_post("First\n\nSecond")

    assert tele.sent[0][1].startswith("ERROR:")
    assert tele.sent[1][1] == "ok:Second"
    assert sink == [tele.sent[0][1], "ok:Second"]
