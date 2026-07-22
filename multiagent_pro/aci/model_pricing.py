#!/usr/bin/env python
"""Pricing registry for models litellm doesn't already know about.

litellm's cost calculator (`litellm.cost_calculator.completion_cost`) only prices models listed
in its bundled `model_prices_and_context_window.json`. Self-hosted / institute-proxied models
(e.g. ASU RC's OpenAI-compatible endpoint) aren't in there, so with `per_instance_cost_limit > 0`
SWE-agent's model layer (`models.py`) re-raises the cost-calc failure as a hard
`ModelConfigurationError` and the run dies on the very first LLM call.

This module persists per-model pricing (pulled once from the provider's own dashboard/model
page) to `custom_model_pricing.json` next to this file, and re-registers it with litellm via
`litellm.register_model()` on every run so cost tracking — and `per_instance_cost_limit` — work
normally instead of being forced to 0.

Callers (`gen_solver_config.py` at config-generation time, `orchestrate.py` at run time) both
call `ensure_registered()`. If a model is neither known to litellm nor in our saved registry,
it raises `UnregisteredModelError` with the exact CLI flags needed to register it — surfaced to
whoever invoked the script (as opposed to blocking on an interactive prompt, since these scripts
are typically driven non-interactively).
"""
import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent / "custom_model_pricing.json"


class UnregisteredModelError(SystemExit):
    """Model has no litellm pricing and none saved in our registry — need info from the user."""


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {}


def _save_registry(reg: dict) -> None:
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n")


def is_known_to_litellm(model_name: str) -> bool:
    import litellm
    try:
        litellm.get_model_info(model_name)
        return True
    except Exception:
        return False


def get_saved_pricing(model_name: str) -> dict | None:
    return _load_registry().get(model_name)


def save_pricing(model_name: str, *, price_per_million: float, context_window: int,
                  max_output_tokens: int | None = None) -> dict:
    """Persist pricing pulled from the provider's model page for `model_name`.

    `price_per_million` is treated as a single blended rate (institute pages like ASU RC's
    typically publish one "indicative value / 1M" rather than separate input/output prices) and
    applied to both input and output tokens.
    """
    per_token = price_per_million / 1_000_000
    entry = {
        "max_tokens": context_window,
        "max_input_tokens": context_window,
        "max_output_tokens": max_output_tokens or context_window,
        "input_cost_per_token": per_token,
        "output_cost_per_token": per_token,
        "litellm_provider": "openai",
        "mode": "chat",
    }
    reg = _load_registry()
    reg[model_name] = entry
    _save_registry(reg)
    return entry


def ensure_registered(model_name: str, *, price_per_million: float | None = None,
                       context_window: int | None = None,
                       max_output_tokens: int | None = None) -> None:
    """Make sure litellm can price `model_name`, registering it if we have (or were just given)
    the numbers. Raises UnregisteredModelError if the model is unknown to litellm, has nothing
    saved, and no pricing was passed in.
    """
    import litellm

    if is_known_to_litellm(model_name):
        return

    if price_per_million is not None and context_window is not None:
        save_pricing(model_name, price_per_million=price_per_million,
                     context_window=context_window, max_output_tokens=max_output_tokens)

    entry = get_saved_pricing(model_name)
    if entry is None:
        raise UnregisteredModelError(
            f"Model {model_name!r} has no litellm pricing entry and nothing saved in "
            f"{REGISTRY_PATH}.\n"
            "Look it up on your institute/provider's model page (context window + price per "
            "1M tokens) and re-run with:\n"
            "  --price-per-million-tokens <value>  --context-window <tokens>\n"
            "(saved once, reused automatically on every future run with this model name)."
        )
    litellm.register_model({model_name: entry})
