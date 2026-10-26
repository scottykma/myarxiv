import json
import logging

from src.config import get, set as config_set, save
from src.interests import (
    add_keywords as merge_keywords,
    canonical_keyword,
    category_help,
    drop_weights,
    parse_categories,
    remove_keywords as drop_keywords,
    validate_max_papers,
    validate_score,
    validate_weight,
)
from src.llm import get_fast

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a research assistant helping a researcher manage their arXiv paper filtering configuration. You can have natural conversation AND execute actions using function calls.

Researcher Profile:
{profile_summary}

Current Config:
{current_config}

--- AVAILABLE FUNCTIONS ---
Call these functions in your response WHEN you need to change the config. You can call multiple functions at once, and you can also write normal text before/after the functions.

/ADD(keyword1, keyword2, ...)
  Add one or more keywords/phrases to the include list. Use this when the user wants to follow new topics.

/REMOVE(keyword1, keyword2, ...)
  Remove one or more keywords from the include list. Use this when the user wants to stop following certain topics.

/EXCLUDE(keyword1, keyword2, ...)
  Add one or more keywords to the exclude list. Use this when the user definitely does NOT want papers on certain topics.

/UNEXCLUDE(keyword1, keyword2, ...)
  Remove keywords from the exclude list. Use this when the user wants to allow previously excluded topics.

/CATS(cat1, cat2, ...)
  Set the arXiv categories to monitor. Valid categories: cs.AI, cs.CL, cs.CV, cs.LG, cs.RO, cs.NE, cs.IR, stat.ML.

/SCORE(n)
  Set the minimum relevance score threshold. n should be 1-10.

/MAX(n)
  Set the maximum number of papers to deliver per day. n should be 1-50.

/WEIGHT(keyword, n)
  Set the importance of an include keyword. n should be 1-5 (3 = core, 2 = related, 1 = default).

--- RULES ---
1. ALWAYS use the function call syntax (/ADD, /REMOVE, etc.) for config changes. NEVER output JSON arrays, JSON objects, or code blocks for actions.
2. When the user asks you to make config changes, call the appropriate function(s) immediately.
3. When the user asks a question or wants to discuss, respond with normal text first, then call functions if appropriate.
4. When you are UNSURE, ask a clarifying question. Do not guess.
5. When the user asks about their current config, answer with text only.
6. You can mix text and function calls in one response.

--- EXAMPLES ---

User: "add DiT"
Response:
/ADD(DiT)

User: "add DiT and remove attention mechanism, add sparse attention"
Response:
Sure, replacing the broad attention mechanism with sparse attention.
/REMOVE(attention mechanism)
/ADD(sparse attention mechanism)

User: "focus on my core areas"
Response:
Based on your publications on video generation and autoregressive image generation,
I suggest removing these broader terms to focus on your specialties:
/REMOVE(convolutional neural network, contrastive learning, unsupervised learning, autoencoder)
These removals will narrow your filter to autoregressive models, diffusion models,
and video/image generation techniques. Does this look right?

User: "yes"
Response:
/REMOVE(convolutional neural network, contrastive learning, unsupervised learning, autoencoder)

User: "what should I add?"
Response:
Based on your recent work on video generation with TempoMaster and NFIG for image
generation, you might consider: 1) "DiT" (Diffusion Transformer) - trending in generation,
2) "flow matching" - popular alternative to diffusion, 3) "world model" - relevant to
video prediction. Would you like me to add any of these?

User: "yes all three"
Response:
/ADD(DiT, flow matching, world model)

--- END EXAMPLES ---"""


def build_system_prompt() -> str:
    profile_name = get("profile.name", "Researcher")
    profile_affiliation = get("profile.affiliation", "")
    profile_interests = get("profile.interests", [])
    profile_pubs = get("profile.recent_papers", [])

    pub_lines = []
    for pub in profile_pubs[:10]:
        pub_lines.append(f"  - [{pub.get('year', '?')}] {pub.get('title', '')}")
    pubs_text = "\n".join(pub_lines) if pub_lines else "  (none)"

    profile_summary = (
        f"Name: {profile_name}\n"
        f"Affiliation: {profile_affiliation}\n"
        f"Stated interests: {', '.join(profile_interests) if profile_interests else '(none)'}\n"
        f"Recent publications:\n{pubs_text}"
    )

    current = [
        f"keywords_include: {get('interests.keywords_include', [])}",
        f"keywords_exclude: {get('interests.keywords_exclude', [])}",
        f"categories: {get('interests.categories', [])}",
        f"max_papers: {get('daily.max_papers', 20)}",
        f"min_score: {get('daily.min_relevance_score', 7)}",
    ]
    return SYSTEM_PROMPT.format(
        profile_summary=profile_summary,
        current_config="\n".join(current),
    )


def parse_response(messages: list[dict]) -> tuple[str, list[dict], str]:
    reasoning = ""
    full_text = ""
    for r, t, _ in _parse_stream(messages):
        reasoning = r
        full_text = t
    return _split_response(full_text, reasoning)


def parse_response_stream(messages: list[dict]):
    for reasoning, text, is_final in _parse_stream(messages):
        if is_final:
            chat, actions, _ = _split_response(text, reasoning)
        else:
            chat, actions = "", []
        yield reasoning, text, chat, actions, is_final


def _parse_stream(messages: list[dict]):
    client = get_fast()

    stream = client.call(
        messages,
        max_tokens=4096,
        stream=True,
        thinking=True,
    )

    reasoning = ""
    full_text = ""
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.reasoning_content:
            reasoning += delta.reasoning_content
        if delta.content:
            full_text += delta.content
        yield reasoning, full_text, False

    yield reasoning, full_text, True


def _split_response(full_text: str, reasoning: str) -> tuple[str, list[dict], str]:
    chat_lines = []
    actions = []
    for line in full_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        action = _parse_function_call(line)
        if action:
            actions.append(action)
        else:
            chat_lines.append(line)

    if not actions:
        actions = _try_parse_json_actions(full_text)
        if actions:
            chat_lines = [l for l in chat_lines if not any(l.strip().startswith(c) for c in ("[", "{", "```"))]

    if not chat_lines and not actions:
        chat_text = "Sorry, I had trouble processing that. Could you rephrase?"
    else:
        chat_text = "\n".join(chat_lines)

    return chat_text, actions, reasoning


def _try_parse_json_actions(text: str) -> list[dict]:
    try:
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(text)
        if isinstance(parsed, list) and all(isinstance(a, dict) and "action" in a for a in parsed):
            return parsed
        if isinstance(parsed, dict) and "action" in parsed:
            return [parsed]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [str(value)]


def execute_action(action: dict, *, persist: bool = True) -> list[tuple[str, str]]:
    act = action.get("action", "none")
    results: list[tuple[str, str]] = []
    changed = False

    if act in ("add_keywords", "add_exclude"):
        key = "interests.keywords_include" if act == "add_keywords" else "interests.keywords_exclude"
        label = "Added" if act == "add_keywords" else "Excluded"
        updated, added, duplicates = merge_keywords(
            list(get(key, [])),
            _as_list(action.get("keywords")),
        )
        if added:
            config_set(key, updated)
            changed = True
            results.append(("green", f"{label}: {', '.join(added)}"))
        if duplicates:
            results.append(("yellow", f"Already in list: {', '.join(duplicates)}"))
        if not added and not duplicates:
            results.append(("yellow", "No keywords provided"))

    elif act in ("remove_keywords", "remove_exclude"):
        key = "interests.keywords_include" if act == "remove_keywords" else "interests.keywords_exclude"
        label = "Removed" if act == "remove_keywords" else "Un-excluded"
        missing_label = "Not found in list" if act == "remove_keywords" else "Not in exclude list"
        updated, removed, missing = drop_keywords(
            list(get(key, [])),
            _as_list(action.get("keywords")),
        )
        if removed:
            config_set(key, updated)
            if act == "remove_keywords":
                weights = dict(get("interests.keyword_weights", {}) or {})
                updated_weights = drop_weights(weights, removed)
                if updated_weights != weights:
                    config_set("interests.keyword_weights", updated_weights)
            changed = True
            results.append(("green", f"{label}: {', '.join(removed)}"))
        if missing:
            results.append(("yellow", f"{missing_label}: {', '.join(missing)}"))
        if not removed and not missing:
            results.append(("yellow", "No keywords provided"))

    elif act == "set_keyword_weight":
        include = list(get("interests.keywords_include", []))
        keyword = canonical_keyword(include, str(action.get("keyword", "")))
        if keyword is None:
            results.append(("red", f"Keyword not in include list: {action.get('keyword', '')}"))
        else:
            try:
                weight = validate_weight(action.get("weight"))
            except ValueError as exc:
                results.append(("red", str(exc)))
            else:
                weights = dict(get("interests.keyword_weights", {}) or {})
                if weights.get(keyword, 1) == weight:
                    results.append(("yellow", f"Weight already {weight} for {keyword}"))
                else:
                    weights[keyword] = weight
                    config_set("interests.keyword_weights", weights)
                    changed = True
                    results.append(("green", f"Weight for {keyword} set to {weight}"))

    elif act == "set_categories":
        valid, invalid = parse_categories(_as_list(action.get("categories")))
        if invalid:
            results.append(("red", f"Unknown categories: {', '.join(invalid)}. Valid: {category_help()}"))
        elif not valid:
            results.append(("red", f"No categories provided. Valid: {category_help()}"))
        else:
            config_set("interests.categories", valid)
            changed = True
            results.append(("green", f"Categories set to: {', '.join(valid)}"))

    elif act == "set_max_papers":
        try:
            value = validate_max_papers(action.get("value"))
        except ValueError as exc:
            results.append(("red", str(exc)))
        else:
            config_set("daily.max_papers", value)
            changed = True
            results.append(("green", f"Max papers set to {value}"))

    elif act == "set_min_score":
        try:
            value = validate_score(action.get("value"))
        except ValueError as exc:
            results.append(("red", str(exc)))
        else:
            config_set("daily.min_relevance_score", value)
            changed = True
            results.append(("green", f"Min score set to {value}"))

    if changed and persist:
        try:
            save()
        except OSError as exc:
            logger.exception("Failed to save config")
            results.append(("red", f"Failed to save config: {exc}"))

    return results


def _parse_function_call(line: str) -> dict | None:
    line = line.strip()

    func_patterns = {
        "/ADD(": "add_keywords",
        "/REMOVE(": "remove_keywords",
        "/EXCLUDE(": "add_exclude",
        "/UNEXCLUDE(": "remove_exclude",
        "/CATS(": "set_categories",
        "/SCORE(": "set_min_score",
        "/MAX(": "set_max_papers",
        "/WEIGHT(": "set_keyword_weight",
    }

    for prefix, action_name in func_patterns.items():
        if line.upper().startswith(prefix):
            inner = line[len(prefix):].rstrip(")")
            if action_name in ("set_max_papers", "set_min_score"):
                try:
                    return {"action": action_name, "value": int(inner.strip())}
                except (ValueError, TypeError):
                    return None
            elif action_name == "set_categories":
                cats = [c.strip() for c in inner.split(",") if c.strip()]
                return {"action": action_name, "categories": cats}
            elif action_name == "set_keyword_weight":
                parts = [part.strip() for part in inner.rsplit(",", 1)]
                if len(parts) != 2:
                    return None
                try:
                    return {"action": action_name, "keyword": parts[0], "weight": int(parts[1])}
                except ValueError:
                    return None
            else:
                keywords = [k.strip() for k in inner.split(",") if k.strip()]
                return {"action": action_name, "keywords": keywords}

    return None
