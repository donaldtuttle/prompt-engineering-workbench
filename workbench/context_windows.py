"""Pinned context windows. Unknown windows are not guessed.

Claude 1M ids were read from platform.claude.com model pages. Other claude-* ids
use 200k, the context-windows page rule for Claude models outside that 1M list.
Names on that list whose API ids were not on a fetched model page stay at 200k,
which can refuse a long prompt and cannot silently enlarge the window.

OpenAI ids were read from developers.openai.com model pages. Dated snapshots of
those ids share the page's window. Other OpenAI ids are unpinned.
"""

import os

# Longest-prefix match is applied by sorting at lookup.
_CLAUDE_1M = (
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
)
_OPENAI = (
    ("gpt-4.1", 1_047_576),
    ("gpt-4o", 128_000),
)


def _id_match(model, prefix):
    # Dated snapshots only. "gpt-4.1-mini" must not inherit the gpt-4.1 window.
    return model == prefix or model.startswith(prefix + "-20")


def claude_model_window(model):
    matches = [prefix for prefix in _CLAUDE_1M if _id_match(model, prefix)]
    if matches:
        return 1_000_000
    if model.startswith("claude-"):
        return 200_000
    raise ValueError("No pinned context window for this Claude model")


def openai_model_window(model):
    matches = [window for prefix, window in _OPENAI if _id_match(model, prefix)]
    if not matches:
        return None
    return min(matches)


def capped_window(documented, env_name):
    """An env value may lower a documented window. It cannot raise one."""
    raw = os.getenv(env_name)
    if raw is None or raw == "":
        return documented, "model"
    try:
        cap = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{env_name} must be an integer") from exc
    if cap < 1:
        raise RuntimeError(f"{env_name} must be positive")
    if cap >= documented:
        return documented, "model"
    return cap, "env_cap"


def ollama_context(show):
    """Read the architecture context length. Do not substitute a 2048 default."""
    info = show.get("model_info") if isinstance(show, dict) else None
    if not isinstance(info, dict):
        raise ValueError("Ollama model info has no context length")
    lengths = {
        key: value
        for key, value in info.items()
        if key.endswith(".context_length") and type(value) is int and value > 0
    }
    arch = info.get("general.architecture")
    chosen = None
    source = None
    if isinstance(arch, str):
        key = f"{arch}.context_length"
        if key in lengths:
            chosen, source = lengths[key], f"model_info:{key}"
    if chosen is None and len(lengths) == 1:
        key, chosen = next(iter(lengths.items()))
        source = f"model_info:{key}"
    if chosen is None:
        raise ValueError("Ollama model context length is missing or ambiguous")
    modelfile = None
    parameters = show.get("parameters")
    if isinstance(parameters, str):
        for line in parameters.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "num_ctx" and parts[1].isdigit():
                modelfile = int(parts[1])
    return {
        "model_context_length": chosen,
        "modelfile_num_ctx": modelfile,
        "source": source,
    }


def receive_gate(*, model, documented, floor, source, budget, counted, count_source, extra=None):
    gate = {
        "model": model,
        "context_floor": floor,
        "model_context_window": documented,
        "context_floor_source": source,
        "budget": budget,
        "counted_input_tokens": counted,
        "count_source": count_source,
    }
    if extra:
        gate.update(extra)
    return gate


def context_window_error(provider, gate):
    budget = gate["budget"]
    counted = gate["counted_input_tokens"]
    err = ValueError(
        f"{provider} input exceeds the context window "
        f"({counted} input tokens, budget {budget})"
    )
    err.receive_gate = gate
    return err
