from datetime import date
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from app.common.telegram import (
    DigestItem,
    add_utm_params,
    append_source_attribution,
    build_digest,
    chunk_text,
)


def test_add_utm_params():
    url = "https://example.com/path"
    new_url = add_utm_params(url, date(2024, 5, 1))
    assert "utm_source=tg_digest" in new_url
    assert "utm_medium=post" in new_url
    assert "utm_campaign=20240501" in new_url


def test_append_source_attribution():
    text = append_source_attribution("Summary", "source")
    assert text.endswith("(@source)")


def test_build_digest_and_chunking():
    item = DigestItem("Hello", "https://example.com", "src")
    digest = build_digest([item], date(2024, 5, 1))
    assert "@src" in digest
    assert "utm_campaign=20240501" in digest
    long_text = "a" * 4100
    chunks = chunk_text(long_text)
    assert len(chunks) == 2
    assert len(chunks[0]) == 4096
