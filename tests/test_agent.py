"""
Milestone 4 tests for agent.py.

Run from the project root with:
    pytest tests/
"""

import json
import os
import sys
from types import SimpleNamespace

# Ensure the project root (parent of this tests/ directory) is importable,
# since no conftest.py or package config adds it to sys.path automatically.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import agent
from utils.data_loader import get_example_wardrobe

LONG_QUERY = (
    "I'm looking for a vintage graphic tee under $30. I mostly wear baggy "
    "jeans and chunky sneakers. What's out there and how would I style it?"
)


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

    def __init__(self, content):
        self.calls = []
        self.chat = _FakeChat(_FakeCompletions(content, self.calls))


# ── Test 1: _parse_query LLM path ────────────────────────────────────────────

def test_parse_query_llm_path_extracts_clean_search_fields(monkeypatch):
    fake_content = json.dumps({
        "description": "vintage graphic tee",
        "size": None,
        "max_price": 30,
    })
    fake_client = FakeGroqClient(content=fake_content)
    monkeypatch.setattr(agent, "_get_groq_client", lambda: fake_client)

    result = agent._parse_query(LONG_QUERY)

    assert result == {
        "description": "vintage graphic tee",
        "size": None,
        "max_price": 30.0,
    }

    call_kwargs = fake_client.calls[-1]
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["model"] == "llama-3.3-70b-versatile"


# ── Test 2: _parse_query fallback path ───────────────────────────────────────

def test_parse_query_uses_fallback_when_groq_fails(monkeypatch):
    def _raise_client():
        raise RuntimeError("Groq unavailable")

    monkeypatch.setattr(agent, "_get_groq_client", _raise_client)

    result = agent._parse_query(LONG_QUERY)

    assert result == {
        "description": "vintage graphic tee",
        "size": None,
        "max_price": 30.0,
    }


# ── Test 3: run_agent stops early on empty search results ───────────────────

def test_run_agent_uses_parsed_values_and_stops_after_empty_search(monkeypatch):
    parsed = {
        "description": "designer ballgown",
        "size": "XXS",
        "max_price": 5.0,
    }
    monkeypatch.setattr(agent, "_parse_query", lambda query: parsed)

    search_calls = []

    def fake_search_listings(description, size, max_price):
        search_calls.append({
            "description": description,
            "size": size,
            "max_price": max_price,
        })
        return []

    def fail_suggest_outfit(*args, **kwargs):
        raise AssertionError("suggest_outfit should not be called")

    def fail_create_fit_card(*args, **kwargs):
        raise AssertionError("create_fit_card should not be called")

    monkeypatch.setattr(agent, "search_listings", fake_search_listings)
    monkeypatch.setattr(agent, "suggest_outfit", fail_suggest_outfit)
    monkeypatch.setattr(agent, "create_fit_card", fail_create_fit_card)

    session = agent.run_agent("anything at all", get_example_wardrobe())

    assert len(search_calls) == 1
    assert search_calls[0] == {
        "description": "designer ballgown",
        "size": "XXS",
        "max_price": 5.0,
    }

    assert session["parsed"] == parsed
    assert session["search_results"] == []
    assert session["error"]
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None
    
# ── Test 4: successful state handoff ────────────────────────────────────────

def test_run_agent_passes_exact_session_values_between_tools(monkeypatch):
    parsed = {
        "description": "graphic tee",
        "size": None,
        "max_price": 30.0,
    }
    listing = {
        "id": "spy_listing",
        "title": "Spy Graphic Tee",
        "description": "Test listing",
        "category": "tops",
        "style_tags": ["graphic tee"],
        "size": "M",
        "condition": "good",
        "price": 24.0,
        "colors": ["black"],
        "brand": None,
        "platform": "depop",
    }
    captured = {}

    monkeypatch.setattr(agent, "_parse_query", lambda query: parsed)
    monkeypatch.setattr(agent, "search_listings", lambda **kwargs: [listing])

    def spy_suggest_outfit(new_item, wardrobe):
        captured["suggest_item"] = new_item
        captured["suggest_wardrobe"] = wardrobe
        return "SPY OUTFIT"

    def spy_create_fit_card(outfit, new_item):
        captured["fit_card_outfit"] = outfit
        captured["fit_card_item"] = new_item
        return "SPY FIT CARD"

    monkeypatch.setattr(agent, "suggest_outfit", spy_suggest_outfit)
    monkeypatch.setattr(agent, "create_fit_card", spy_create_fit_card)

    session = agent.run_agent("anything at all", get_example_wardrobe())

    assert session["error"] is None
    assert session["selected_item"] is listing
    assert captured["suggest_item"] is session["selected_item"]
    assert captured["suggest_wardrobe"] is session["wardrobe"]
    assert captured["fit_card_item"] is session["selected_item"]
    assert captured["fit_card_outfit"] is session["outfit_suggestion"]
    assert session["outfit_suggestion"] == "SPY OUTFIT"
    assert session["fit_card"] == "SPY FIT CARD"
