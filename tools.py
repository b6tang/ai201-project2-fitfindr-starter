"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def _tokenize_size(size_str: str) -> list[str]:
    """Split a size string into normalized tokens, keeping decimals (e.g. '8.5') intact."""
    return re.findall(r"\d+\.\d+|[a-z0-9]+", size_str.lower())


def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    filtered = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None:
            requested_tokens = set(_tokenize_size(size))
            listing_size_tokens = set(_tokenize_size(item.get("size", "")))
            if not requested_tokens or not requested_tokens.issubset(listing_size_tokens):
                continue
        filtered.append(item)

    query_keywords = set(re.findall(r"[a-z0-9]+", description.lower()))
    if not query_keywords:
        return []

    scored = []
    for item in filtered:
        searchable_parts = [
            item.get("title") or "",
            item.get("description") or "",
            item.get("category") or "",
            " ".join(item.get("style_tags") or []),
            " ".join(item.get("colors") or []),
            item.get("brand") or "",
        ]
        searchable_text = " ".join(searchable_parts).lower()
        item_words = set(re.findall(r"[a-z0-9]+", searchable_text))

        matched_keywords = query_keywords & item_words
        score = len(matched_keywords)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_lines = [f"- Title: {new_item.get('title')}"]
    if new_item.get("category"):
        item_lines.append(f"- Category: {new_item['category']}")
    if new_item.get("colors"):
        item_lines.append(f"- Colors: {', '.join(new_item['colors'])}")
    if new_item.get("style_tags"):
        item_lines.append(f"- Style tags: {', '.join(new_item['style_tags'])}")
    if new_item.get("condition"):
        item_lines.append(f"- Condition: {new_item['condition']}")
    if new_item.get("price") is not None:
        item_lines.append(f"- Price: ${new_item['price']}")
    item_description = "\n".join(item_lines)

    wardrobe_items = wardrobe.get("items", [])

    if wardrobe_items:
        wardrobe_lines = []
        for w in wardrobe_items:
            parts = [w.get("name", "")]
            if w.get("category"):
                parts.append(f"({w['category']})")
            if w.get("colors"):
                parts.append(f"colors: {', '.join(w['colors'])}")
            if w.get("style_tags"):
                parts.append(f"style: {', '.join(w['style_tags'])}")
            if w.get("notes"):
                parts.append(f"notes: {w['notes']}")
            wardrobe_lines.append("- " + " | ".join(parts))
        wardrobe_description = "\n".join(wardrobe_lines)

        prompt = (
            "A user is considering buying this thrifted item:\n"
            f"{item_description}\n\n"
            "Here is the user's current wardrobe:\n"
            f"{wardrobe_description}\n\n"
            "Suggest exactly 1 or 2 complete outfits that pair the new item with specific, "
            "named pieces from the wardrobe above. Only reference pieces that are "
            "actually listed in the wardrobe — do not invent items the user doesn't own. "
            "Use no more than 2 sentences per outfit. Do not include an introduction, "
            "headings, bullet points, brand examples, or disclaimers — just the outfit "
            "sentences."
        )
    else:
        prompt = (
            "A user is considering buying this thrifted item:\n"
            f"{item_description}\n\n"
            "The user has no wardrobe items on file yet. Give general styling advice "
            "for this item in 3 to 5 short sentences: what kinds of pieces would pair "
            "well with it, what vibe or aesthetic it suits, and how they might build an "
            "outfit around it. Do not claim the user owns any specific items. Do not "
            "include an introduction, headings, bullet points, brand examples, "
            "disclaimers, or a long styling guide — just the short advice."
        )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )

    content = response.choices[0].message.content
    if content and content.strip():
        return content.strip()

    return f"Try styling the {new_item.get('title', 'new item')} with neutral basics, denim, or simple layers for an easy, versatile look."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return "Cannot create a fit card: no outfit suggestion was provided."

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "a resale app")

    item_lines = [f"- Title: {title}", f"- Platform: {platform}"]
    if price is not None:
        item_lines.append(f"- Price: ${price}")
    item_description = "\n".join(item_lines)

    prompt = (
        "Write a short social media caption (2-4 sentences) for an OOTD / thrift-find "
        "post, like a real person casually sharing their outfit — not a product listing.\n\n"
        f"Item details:\n{item_description}\n\n"
        f"Outfit styling notes:\n{outfit.strip()}\n\n"
        "Naturally mention the item's title, price, and platform once each, and capture "
        "the outfit vibe in specific terms. Use the exact item title verbatim exactly as "
        "given in Item details above — do not shorten, paraphrase, or abbreviate it. Use "
        "the exact listed price and exact platform name as given, each mentioned once. "
        "Do not use headings, bullet points, quotation marks, hashtags, disclaimers, or "
        "explanations of the task — just the caption text."
    )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
    )

    content = response.choices[0].message.content
    if content and content.strip():
        return content.strip()

    price_text = f"${price}" if price is not None else "a steal"
    return (
        f"Just scored the {title} for {price_text} on {platform} and I'm already "
        "obsessed with how it fits into my rotation. This look has an easy, "
        "thrifted vibe that I’ll be repeating."
    )
