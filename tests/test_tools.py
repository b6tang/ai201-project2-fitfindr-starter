"""
Milestone 3 tests for tools.py.

Run from the project root with:
    pytest tests/
"""

import os
import sys
from types import SimpleNamespace

# Ensure the project root (parent of this tests/ directory) is importable,
# since no conftest.py or package config adds it to sys.path automatically.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import tools
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


# ── Fake Groq client (no network, no API key required) ─────────────────────

class _FakeCompletions:
    def __init__(self, content, calls):
        self._content = content
        self._calls = calls

    def create(self, model, messages, **kwargs):
        self._calls.append({"model": model, "messages": messages, **kwargs})
        message = SimpleNamespace(content=self._content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeGroqClient:
    """Deterministic stand-in for the real Groq client, records every prompt sent."""

    def __init__(self, content="This is a fake styling suggestion."):
        self.calls = []
        self.chat = _FakeChat(_FakeCompletions(content, self.calls))

    @property
    def last_prompt(self):
        return self.calls[-1]["messages"][0]["content"]


# ── Tool 1: search_listings ─────────────────────────────────────────────────

def test_search_listings_normal_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) >= 1


def test_search_listings_no_results_returns_empty_list():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_listings_price_filter_is_respected():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_listings_size_m_matches_slash_m_listing():
    results = search_listings("tee", size="M", max_price=None)
    matches = [item for item in results if item["id"] == "lst_002"]
    assert len(matches) == 1
    assert matches[0]["size"] == "S/M"


# ── Tool 2: suggest_outfit ───────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe_returns_non_empty_string(monkeypatch):
    fake_client = FakeGroqClient(content="General styling advice for the new item.")
    monkeypatch.setattr(tools, "_get_groq_client", lambda: fake_client)

    new_item = {
        "title": "Vintage Windbreaker",
        "category": "outerwear",
        "colors": ["purple", "teal"],
        "style_tags": ["90s", "vintage"],
        "condition": "good",
        "price": 40.0,
    }
    empty_wardrobe = get_empty_wardrobe()

    result = suggest_outfit(new_item, empty_wardrobe)

    assert isinstance(result, str)
    assert result.strip() != ""

    prompt = fake_client.last_prompt.lower()
    assert "no wardrobe items" in prompt
    assert "general styling advice" in prompt


def test_suggest_outfit_normal_wardrobe_prompt_includes_real_item_name(monkeypatch):
    fake_client = FakeGroqClient(content="Pair it with your denim jacket and white sneakers.")
    monkeypatch.setattr(tools, "_get_groq_client", lambda: fake_client)

    new_item = {
        "title": "Graphic Tee — 2003 Tour Bootleg Style",
        "category": "tops",
        "colors": ["black"],
        "style_tags": ["graphic tee", "vintage"],
        "condition": "good",
        "price": 24.0,
    }
    example_wardrobe = get_example_wardrobe()

    result = suggest_outfit(new_item, example_wardrobe)

    assert isinstance(result, str)
    assert result.strip() != ""

    prompt = fake_client.last_prompt
    wardrobe_names = [item["name"] for item in example_wardrobe["items"]]
    assert any(name in prompt for name in wardrobe_names)


# ── Tool 3: create_fit_card ──────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_without_calling_groq(monkeypatch):
    fake_client = FakeGroqClient()
    monkeypatch.setattr(tools, "_get_groq_client", lambda: fake_client)

    new_item = {
        "title": "Denim Jacket — Light Wash, Cropped",
        "price": 42.0,
        "platform": "poshmark",
    }

    result = create_fit_card("   ", new_item)

    assert isinstance(result, str)
    assert result.strip() != ""
    assert fake_client.calls == []


def test_create_fit_card_normal_input_returns_fake_completion_and_builds_prompt(monkeypatch):
    fake_client = FakeGroqClient(content="Just thrifted this jacket and it's giving 90s vibes.")
    monkeypatch.setattr(tools, "_get_groq_client", lambda: fake_client)

    new_item = {
        "title": "Denim Jacket — Light Wash, Cropped",
        "price": 42.0,
        "platform": "poshmark",
    }
    outfit = "Pair with the vintage band tee and dark carpenter jeans."

    result = create_fit_card(outfit, new_item)

    assert result == "Just thrifted this jacket and it's giving 90s vibes."

    prompt = fake_client.last_prompt
    assert new_item["title"] in prompt
    assert str(new_item["price"]) in prompt
    assert new_item["platform"] in prompt
