"""LLM base_url normalization: ACES appends ``/v1/chat/completions``, so a
base_url that ALREADY ends in ``/v1`` (the standard OpenAI/OpenRouter base)
must not produce a doubled ``/v1/v1/...``. Both conventions must work.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aces.runtime import LLMAgentRuntime


def test_base_url_normalization_handles_both_conventions():
    cases = {
        # host form (ACES convention) — unchanged
        "https://openrouter.ai/api": "https://openrouter.ai/api",
        "https://api.openai.com": "https://api.openai.com",
        "https://api.openai.com/": "https://api.openai.com",
        # full OpenAI-style base ending in /v1 — trailing /v1 stripped
        "https://openrouter.ai/api/v1": "https://openrouter.ai/api",
        "https://openrouter.ai/api/v1/": "https://openrouter.ai/api",
        "http://localhost:11434/v1": "http://localhost:11434",
    }
    for given, expect in cases.items():
        rt = LLMAgentRuntime(model="m", base_url=given)
        assert rt.base_url == expect, f"{given} -> {rt.base_url} != {expect}"
        # The effective chat endpoint must contain exactly one /v1/.
        url = f"{rt.base_url}/v1/chat/completions"
        assert url.count("/v1/") == 1, url


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
