"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import re

from tools import search_listings, suggest_outfit, create_fit_card, _get_groq_client


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def _fallback_parse_query(query: str) -> dict:
    """Deterministic regex-based parser, used if the LLM parse fails or is invalid."""
    working_text = query

    price_match = re.search(r"under\s*\$(\d+(?:\.\d+)?)", working_text, re.IGNORECASE)
    max_price = None
    if price_match:
        max_price = float(price_match.group(1))
        working_text = working_text[: price_match.start()] + working_text[price_match.end() :]

    size_match = re.search(r"(?:in\s+)?size\s+([A-Za-z0-9/.\-]+)", working_text, re.IGNORECASE)
    size = None
    if size_match:
        size = size_match.group(1)
        working_text = working_text[: size_match.start()] + working_text[size_match.end() :]

    leading_phrases = r"^(?:i'?m\s+looking\s+for|looking\s+for|find\s+me|show\s+me)\s+(?:a|an|the)?\s*"
    working_text = re.sub(leading_phrases, "", working_text.strip(), flags=re.IGNORECASE)

    trailing_clauses = (
        r"\b(?:i\s+mostly\s+wear|i\s+usually\s+wear|my\s+wardrobe|"
        r"what'?s\s+out\s+there|how\s+would\s+i\s+style).*$"
    )
    working_text = re.sub(trailing_clauses, "", working_text, flags=re.IGNORECASE | re.DOTALL)

    description = re.sub(r"\s+", " ", working_text).strip(" \t\n.,;:!?-")

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural-language query
    using an LLM, falling back to a deterministic regex parser on any failure.
    """
    prompt = (
        "Extract search filters from this clothing shopping request:\n\n"
        f'"{query}"\n\n'
        "Return a JSON object with exactly these keys:\n"
        '- "description": string — only the clothing item the user wants to search for. '
        "Do not include statements about what the user already owns, usually wears, "
        "styling preferences, or follow-up questions.\n"
        '- "size": the requested size for the item as a string, or null if not specified.\n'
        '- "max_price": the requested maximum dollar amount as a number, or null if not specified.\n\n'
        "Do not invent filters that are not present in the request. Return valid JSON only."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)

        description = parsed.get("description")
        size = parsed.get("size")
        max_price = parsed.get("max_price")

        if not isinstance(description, str) or not description.strip():
            raise ValueError("description must be a non-empty string")
        if size is not None and not isinstance(size, str):
            raise ValueError("size must be a string or null")
        if max_price is not None and (
            isinstance(max_price, bool)
            or not isinstance(max_price, (int, float))
        ):
            raise ValueError("max_price must be a number or null")
        
        return {
            "description": description.strip(),
            "size": size,
            "max_price": float(max_price) if max_price is not None else None,
        }
    except Exception:
        return _fallback_parse_query(query)


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    """
    session = _new_session(query, wardrobe)

    session["parsed"] = _parse_query(query)

    session["search_results"] = search_listings(
        description=session["parsed"]["description"],
        size=session["parsed"]["size"],
        max_price=session["parsed"]["max_price"],
    )

    if not session["search_results"]:
        session["error"] = (
            "No listings found. Try different keywords, a different size, or a higher budget."
        )
        return session

    session["selected_item"] = session["search_results"][0]
    session["outfit_suggestion"] = suggest_outfit(session["selected_item"], session["wardrobe"])
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
