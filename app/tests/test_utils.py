import pytest

from app.common.utils import (
    calculate_cost,
    count_tokens,
    extract_links,
    html_escape,
    split_topics,
)


def test_extract_links():
    text = "Check https://example.com and also <a href='https://example.org'>org</a>."
    assert extract_links(text) == [
        "https://example.com",
        "https://example.org",
    ]


def test_split_topics():
    text = "First topic\n\nSecond topic\ncontinues\n\nThird"
    assert split_topics(text) == [
        "First topic",
        "Second topic\ncontinues",
        "Third",
    ]


def test_html_escape():
    assert html_escape("<tag>") == "&lt;tag&gt;"


def test_token_and_cost():
    text = "hello, world!"
    tokens = count_tokens(text)
    assert tokens == 4
    cost = calculate_cost(tokens, rate_per_1k=2.0)
    assert pytest.approx(cost, rel=1e-6) == 0.008
