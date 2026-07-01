# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
Loads the mock clothing listings, filters them by the optional size and maximum price, then ranks relevant matches using keyword overlap with the user's requested description. It returns the matching listings with the most relevant result first.

**Input parameters:**
- `description` (str): description: A short search phrase describing the item the user wants, such as "vintage graphic tee". It is matched against multiple listing fields, including title, description, category, style_tags, colors, and brand; it is not limited to a listing's description field, such as `"vintage graphic tee"`.
- `size` (str | None): Optional requested size. Matching is case-insensitive; a requested size such as `"M"` can match a listing size such as `"S/M"`. `None` skips size filtering.
- `max_price` (float | None): Optional maximum price in dollars. The price limit is inclusive; `None` skips price filtering.

**What it returns:**
A `list[dict]` of matching listing dictionaries, sorted by relevance with the best match first. Each listing contains `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), and `platform` (str).

**What happens if it fails or returns nothing:**
If no listing matches, the tool returns `[]` rather than raising an exception. The agent stores the empty result, stops the workflow before calling the other tools, and tells the user to try different keywords, a different size, or a higher budget.

---

### Tool 2: suggest_outfit

**What it does:**
Uses the selected listing and the user's wardrobe to generate one or two complete outfit suggestions. When wardrobe items are available, the suggestions name compatible pieces from that wardrobe. It calls Groq's `llama-3.3-70b-versatile` model with the selected listing and wardrobe details.

**Input parameters:**
- `new_item` (dict): The single listing selected by the agent from `search_results`, usually the top result (`search_results[0]`).
- `wardrobe` (dict): A wardrobe dictionary with an `items` list. Each wardrobe item has `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), and optional `notes` (str | None).

**What it returns:**
A non-empty `str` containing one or two outfit suggestions. With a non-empty wardrobe, it recommends specific named wardrobe pieces; with an empty wardrobe, it returns general styling advice for the selected item, such as compatible clothing categories, colors, and style vibe.

**What happens if it fails or returns nothing:**
An empty wardrobe is treated as a normal case rather than an error. In that case, the tool returns general styling advice instead of returning an empty string. If no suitable outfit suggestion can be generated for any reason, it returns a non-empty fallback styling message so the user still receives useful guidance.

---

### Tool 3: create_fit_card

**What it does:**
Uses the outfit suggestion and selected listing to generate a short, casual caption suitable for an Instagram or TikTok outfit post. The caption should sound like an OOTD post rather than a product description. It calls Groq's `llama-3.3-70b-versatile` model with the selected listing and outfit suggestion.

**Input parameters:**
- `outfit` (str): The non-empty outfit suggestion returned by `suggest_outfit`.
- `new_item` (dict): The selected listing dictionary, used to include the item's title, price, platform, and style details.

**What it returns:**
A `str` containing a 2–4 sentence fit card. It naturally mentions the item name, price, and platform once each, describes the outfit vibe, and varies its wording for different inputs.

**What happens if it fails or returns nothing:**
If `outfit` is empty or contains only whitespace, the tool returns a descriptive error message string instead of raising an exception. In the normal agent flow, the agent should not call this tool with an empty outfit because `suggest_outfit()` returns non-empty text. If it does occur, `run_agent()` stores the returned error string in `session["fit_card"]`, and `app.py` displays it in the third output panel.


---

## Planning Loop

**How does your agent decide which tool to call next?**

The agent starts by creating a session and calling a private `_parse_query()` helper to extract `description`, `size`, and `max_price` from the user's natural-language query. `_parse_query()` uses Groq's `llama-3.3-70b-versatile` model in JSON mode to return those three fields. If the Groq call fails, the JSON is invalid, or validation fails, `_parse_query()` falls back to deterministic regular-expression parsing that extracts price and size and removes common request or wardrobe-context phrases.

The agent calls `search_listings(description, size, max_price)` first because the later tools need one specific listing.

After the search returns, the agent checks whether `search_results` is empty. If it is empty, it stores a no-results message in `session["error"]` and returns immediately without calling `suggest_outfit` or `create_fit_card`. If results exist, the agent stores the full results list, sets `selected_item = search_results[0]`, and calls `suggest_outfit(selected_item, wardrobe)`.

The agent stores the returned outfit text in `session["outfit_suggestion"]`. It then calls `create_fit_card(outfit_suggestion, selected_item)`, stores the returned caption in `session["fit_card"]`, and returns the completed session. An empty wardrobe does not stop the flow because `suggest_outfit` returns general styling advice instead of an empty result.

---

## State Management

**How does information from one tool get passed to the next?**

The agent keeps one session dictionary for the full request. It stores the original `query`, the selected `wardrobe`, parsed search values in `parsed`, the full `search_results` list, the chosen `selected_item`, the generated `outfit_suggestion`, the final `fit_card`, and an `error` message when a step cannot continue.

`search_listings()` returns a list of listing dictionaries, which is saved in `session["search_results"]`. The agent saves the first listing as `session["selected_item"]` and passes that exact dictionary, together with `session["wardrobe"]`, to `suggest_outfit()`. The returned suggestion is saved in `session["outfit_suggestion"]` and passed with the same selected item to `create_fit_card()`. This avoids asking the user to repeat listing or wardrobe information.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | The tool returns `[]`. The agent sets `session["error"]` to a message such as: “No listings found. Try different keywords, a different size, or a higher budget.” It returns early and does not call the later tools. |
| suggest_outfit | Wardrobe is empty | The tool does not fail or stop the workflow. It returns general styling advice for the selected item instead of naming existing wardrobe pieces. The agent stores that advice in `session["outfit_suggestion"]`, continues to `create_fit_card`. |
| create_fit_card | Outfit input is empty or whitespace-only | The tool returns a descriptive error string instead of crashing. This should not occur in the normal agent flow because `suggest_outfit` returns a non-empty fallback message. If it does occur, `run_agent()` stores the returned string in `session["fit_card"]`, and the interface displays it in the third panel. |

---

## Architecture

```
User query
    │
    ▼
Planning Loop
    │
    ├─► _parse_query(query)
    │       ├─ Groq JSON parsing → description, size, max_price
    │       └─ failure or invalid JSON → regex fallback
    │
    ├─► search_listings(description, size, max_price)
    │       │
    │       ├─ results=[]
    │       │    └─► Session: error = "No listings found..."
    │       │         └─► Return session early
    │       │
    │       └─ results=[listing, ...]
    │            │
    │            ▼
    │        Session: search_results = results
    │                 selected_item = results[0]
    │            │
    ├─► suggest_outfit(selected_item, wardrobe)
    │       │
    │       ├─ empty wardrobe → general styling advice
    │       │
    │       ▼
    │   Session: outfit_suggestion = "..."
    │       │
    └─► create_fit_card(outfit_suggestion, selected_item)
            │
            ▼
        Session: fit_card = "..."
            │
            ▼
        Return session
```
---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

Claude Agent will generate the code one function at a time. Each prompt will include the matching Tool section from `planning.md`, the function signature and TODO in `tools.py`, and the relevant data source or schema. ChatGPT and other LLMs will mainly be used to explain the starter code and help check the logic.

For `search_listings`, the prompt will include `load_listings()` from `data_loader.py` and the listings structure. The expected result is a function that filters by description, size, and price, ranks matching listings by relevance, and returns `[]` when there are no matches.

For `suggest_outfit`, the prompt will include the wardrobe schema and selected listing structure. It should use named wardrobe items when available, but still give general styling advice when the wardrobe is empty. For `create_fit_card`, the prompt will include the outfit suggestion and selected listing structure. It should return a short social-media-style caption, or a clear error message when the outfit input is empty.

The generated functions will be checked with the provided tests plus a few normal and failure cases before moving on.

**Milestone 4 — Planning loop and state management:**

Claude Agent will receive the Planning Loop, State Management, Error Handling, Architecture, and Complete Interaction sections from `planning.md`, together with the TODOs in `agent.py` and `app.py`.

The implementation should follow the planned flow: parse the query, call `search_listings()`, stop early when there are no results, save the first result as `selected_item`, pass that item and the wardrobe into `suggest_outfit()`, and then pass the outfit suggestion and same item into `create_fit_card()`. The parser implementation should use a private `_parse_query()` helper that calls Groq in JSON mode to extract `description`, `size`, and `max_price`, with deterministic regex parsing as a fallback when the Groq response is unavailable or invalid.

The final check is one normal query and one no-results query. The normal query should produce a listing, outfit suggestion, and fit card. The no-results query should set an error and stop before the later tools run.The agent workflow is also verified in `tests/test_agent.py` using mocked Groq and mocked tool functions. These tests confirm structured query parsing, regex fallback behavior, early return after empty search results, and exact state handoff through `session["selected_item"]` and `session["outfit_suggestion"]`.

---

## A Complete Interaction (Step by Step)

FitFindr reads a user's clothing request and calls `search_listings` to find listings that match the requested description, size, and budget. When the search finds a match, it passes the top listing and the user's wardrobe to `suggest_outfit`, then passes the outfit suggestion and the same listing to `create_fit_card` to generate a shareable caption. If no listings match, FitFindr stops and suggests changing the description, size, or budget; if the wardrobe is empty, it gives general styling advice instead.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent calls `_parse_query(query)` before searching. For this query, the parser returns:

`{"description": "vintage graphic tee", "size": None, "max_price": 30.0}`

The helper uses Groq JSON parsing first and falls back to deterministic regex parsing if the Groq call, JSON parsing, or validation fails.

It then calls:

`search_listings(description="vintage graphic tee", size=None, max_price=30.0)`

The tool filters out listings over $30, scores the remaining listings by keyword relevance, and returns matching listing dictionaries sorted from most to least relevant. The agent saves the full list in `session["search_results"]`, selects the first result, and saves that exact listing dictionary in `session["selected_item"]`. If the returned list is empty, the agent stores a helpful error telling the user to try broader keywords or a higher budget, then returns immediately without calling the next two tools.


**Step 2:**
Because a matching listing was found, the agent calls:

`suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`

For this interaction, `session["wardrobe"]` is the example wardrobe, which includes baggy straight-leg jeans and chunky white sneakers. The tool returns a non-empty outfit suggestion that pairs the selected graphic tee with specific wardrobe items, and the agent saves that text in `session["outfit_suggestion"]`.

**Step 3:**
The agent calls:

`create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`

The tool uses the selected listing and outfit suggestion to return a short 2–4 sentence social-media-style caption. The agent saves that caption in `session["fit_card"]`.

**Final output to user:**  
The interface shows the selected top listing in the first panel, including its title, size, condition, price, and platform. The second panel shows the outfit suggestion using the user’s wardrobe, and the third panel shows the generated fit card caption.