"""AI-powered text polishing for trevo voice-to-text output."""
from __future__ import annotations

import asyncio
from typing import Optional

from utils.logger import logger

from utils.platform_utils import AppContext
from utils.text_utils import is_short_phrase, remove_filler_words


# ---------------------------------------------------------------------------
# Context-aware system prompts
# ---------------------------------------------------------------------------

_CONTEXT_PROMPTS: dict[str, str] = {
    "email": (
        "You are a writing assistant polishing dictated text for an email. "
        "Produce clear, professional prose with proper greeting/closing conventions. "
        "Fix grammar and remove speech artifacts, but keep the author's intent and tone."
    ),
    "chat": (
        "You are polishing dictated text for a chat message. "
        "Keep it concise and conversational. Fix obvious errors but preserve "
        "informal tone. Do NOT add greetings or sign-offs."
    ),
    "code": (
        "You are polishing a dictated code comment or documentation string. "
        "Use technical language where appropriate. Preserve any code-related "
        "terms, variable names, and formatting hints the user mentioned."
    ),
    "document": (
        "You are polishing dictated text for a document or word processor. "
        "Produce well-structured, grammatically correct prose suitable for "
        "professional or academic documents."
    ),
    "ai_prompt": (
        "You are polishing dictated text that will be used as an AI prompt. "
        "Make the instructions clear and unambiguous. Preserve technical "
        "specificity and the user's original intent exactly."
    ),
    "generic": (
        "You are polishing dictated text. Fix grammar, remove filler words "
        "and self-corrections, and produce clean readable text while "
        "preserving the author's meaning and tone."
    ),
}

_SHARED_INSTRUCTIONS = (
    "\n\nRules:\n"
    "- Remove filler words (um, uh, like, you know, basically, etc.).\n"
    "- Resolve self-corrections (e.g. 'go left, I mean right' → 'go right').\n"
    "- Fix grammar and punctuation.\n"
    "- Do NOT add information the speaker did not say.\n"
    "- Return ONLY the polished text, no commentary.\n"
)


# ---------------------------------------------------------------------------
# Provider helpers
# ---------------------------------------------------------------------------

_openai_client = None
_anthropic_client = None


def _get_openai_client(api_key: str):
    """Reuse a single AsyncOpenAI client across calls."""
    global _openai_client
    import openai
    if _openai_client is None or _openai_client.api_key != api_key:
        _openai_client = openai.AsyncOpenAI(api_key=api_key)
    return _openai_client


def _get_anthropic_client(api_key: str):
    """Reuse a single AsyncAnthropic client across calls."""
    global _anthropic_client
    import anthropic
    if _anthropic_client is None or _anthropic_client.api_key != api_key:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


async def _call_openai(prompt: str, system: str, model: str, api_key: str) -> str:
    """Call OpenAI-compatible chat completion."""
    try:
        import openai  # noqa: F811
    except ImportError:
        raise RuntimeError("openai package is not installed. Run: pip install openai")

    client = _get_openai_client(api_key)
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    return response.choices[0].message.content.strip()


async def _call_anthropic(prompt: str, system: str, model: str, api_key: str) -> str:
    """Call Anthropic messages API."""
    try:
        import anthropic  # noqa: F811
    except ImportError:
        raise RuntimeError("anthropic package is not installed. Run: pip install anthropic")

    client = _get_anthropic_client(api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.content[0].text.strip()


async def _call_ollama(prompt: str, system: str, model: str, base_url: str) -> str:
    """Call a local Ollama instance."""
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx package is not installed. Run: pip install httpx")

    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


# ---------------------------------------------------------------------------
# TextPolisher
# ---------------------------------------------------------------------------

class TextPolisher:
    """Polishes raw dictated text using an LLM or local heuristics.

    Parameters
    ----------
    provider : str
        One of ``"openai"``, ``"anthropic"``, or ``"ollama"``.
    api_key : str | None
        API key for OpenAI / Anthropic. Not needed for Ollama.
    model : str | None
        Override the default model for the chosen provider.
    ollama_base_url : str
        Base URL for the local Ollama server.
    short_phrase_threshold : int
        Word-count threshold below which the LLM is skipped.
    """

    _DEFAULT_MODELS: dict[str, str] = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "ollama": "llama3.2",
    }

    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        ollama_base_url: str = "http://localhost:11434",
        short_phrase_threshold: int = 10,
    ) -> None:
        self.provider = provider.lower()
        if self.provider not in self._DEFAULT_MODELS:
            raise ValueError(f"Unsupported provider '{provider}'. Choose from: {list(self._DEFAULT_MODELS)}")
        self.api_key = api_key
        self.model = model or self._DEFAULT_MODELS[self.provider]
        self.ollama_base_url = ollama_base_url
        self.short_phrase_threshold = short_phrase_threshold
        logger.info("TextPolisher initialised (provider={}, model={})", self.provider, self.model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def polish(self, raw_text: str, context: Optional[AppContext] = None) -> str:
        """Polish *raw_text* and return cleaned text.

        For short phrases (fewer than ``short_phrase_threshold`` words), only
        local heuristic cleanup is performed (no LLM call).

        Parameters
        ----------
        raw_text : str
            The raw transcription from the STT engine.
        context : AppContext | None
            Optional application context used to tailor the polish prompt.
        """
        if not raw_text or not raw_text.strip():
            return raw_text

        text = raw_text.strip()

        # Short phrases — local cleanup only
        if is_short_phrase(text, self.short_phrase_threshold):
            cleaned = remove_filler_words(text)
            logger.debug("Short phrase — local cleanup only: '{}' → '{}'", text, cleaned)
            return cleaned

        # Build prompt
        app_type = context.app_type if context else "generic"
        system_prompt = _CONTEXT_PROMPTS.get(app_type, _CONTEXT_PROMPTS["generic"]) + _SHARED_INSTRUCTIONS
        user_prompt = f"Polish the following dictated text:\n\n{text}"

        logger.debug("Polishing with {} (context={})", self.provider, app_type)

        try:
            polished = await self._call_llm(user_prompt, system_prompt)
            logger.debug("Polished result: '{}'", polished[:120])
            return polished
        except Exception:
            logger.exception("LLM polish failed — falling back to local cleanup")
            return remove_filler_words(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str, system: str) -> str:
        if self.provider == "openai":
            return await _call_openai(prompt, system, self.model, self._require_key())
        elif self.provider == "anthropic":
            return await _call_anthropic(prompt, system, self.model, self._require_key())
        elif self.provider == "ollama":
            return await _call_ollama(prompt, system, self.model, self.ollama_base_url)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _require_key(self) -> str:
        if not self.api_key:
            raise ValueError(f"API key required for provider '{self.provider}'")
        return self.api_key
