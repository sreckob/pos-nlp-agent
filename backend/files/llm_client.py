"""
llm_client.py — unified LLM interface
======================================
All LLM calls go through this module. Swap providers by changing
LLM_MODEL in .env — no code changes needed.

Supported model strings (examples):
  Anthropic:  claude-sonnet-4-6          (default)
  Gemini:     gemini/gemini-1.5-flash
  Mistral:    mistral/mistral-small-latest

Vision calls (dispute receipt OCR) go through complete_vision()
which defaults to VISION_MODEL (Claude by default — most reliable
for document understanding; swap only if your provider supports it).

API keys are read automatically from environment by litellm:
  ANTHROPIC_API_KEY  — for Claude
  GOOGLE_API_KEY     — for Gemini
  MISTRAL_API_KEY    — for Mistral
"""

import logging
import os
from typing import Dict, List

import litellm
import anthropic

from config import settings

logger = logging.getLogger(__name__)

# Suppress litellm's verbose startup logging
litellm.set_verbose = False

# Inject provider API keys so litellm finds them regardless of
# how the env was loaded (dotenv vs Railway vs shell export).
if settings.ANTHROPIC_API_KEY:
    os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
if settings.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"]    = settings.GOOGLE_API_KEY
if settings.MISTRAL_API_KEY:
    os.environ["MISTRAL_API_KEY"]   = settings.MISTRAL_API_KEY


# ── Text completion (all non-vision nodes) ────────────────────

def complete(
    system:      str,
    messages:    List[Dict],
    max_tokens:  int   = 1024,
    temperature: float = 0.0,
    model:       str   = None,
) -> str:
    """
    Single LLM call. Returns the assistant's text response.

    system   — system prompt (LiteLLM converts to the right format per provider)
    messages — list of {role, content} dicts (user / assistant alternating)
    model    — override; defaults to settings.LLM_MODEL
    """
    target_model = model or settings.LLM_MODEL
    full_messages = [{"role": "system", "content": system}] + messages

    try:
        response = litellm.completion(
            model       = target_model,
            messages    = full_messages,
            max_tokens  = max_tokens,
            temperature = temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM call failed (model={target_model}): {e}")
        raise


# ── Vision completion (dispute receipt OCR) ───────────────────
# Uses the Anthropic SDK directly — multimodal format is reliable
# and Claude Vision is the strongest for document understanding.
# Set VISION_MODEL in .env to swap (must be a Claude model string).

_anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def complete_vision(
    system:      str,
    messages:    List[Dict],
    max_tokens:  int   = 1024,
    temperature: float = 0.0,
) -> str:
    """
    Multimodal LLM call (text + base64 image).
    Always uses VISION_MODEL via the Anthropic SDK.
    messages may contain content blocks of type 'image' and 'text'.
    """
    try:
        response = _anthropic_client.messages.create(
            model       = settings.VISION_MODEL,
            max_tokens  = max_tokens,
            temperature = temperature,
            system      = system,
            messages    = messages,
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Vision LLM call failed (model={settings.VISION_MODEL}): {e}")
        raise
