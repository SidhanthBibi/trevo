"""Conversational AI engine for trevo.

This is the brain of trevo. Instead of just transcribing speech,
it understands INTENT — distinguishing between:

1. Content dictation: "The quarterly results show a 15% increase..."
2. Instructions: "...now make that a formal letter"
3. Editing: "replace the first paragraph with a summary"
4. Meta commands: "undo", "read it back", "start over"

The engine buffers the entire conversation, detects when the user
switches from content to instruction, and routes accordingly.

Runs 100% locally via Ollama, or optionally via cloud APIs.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from utils.logger import logger


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

class Intent(Enum):
    """What the user is trying to do."""
    DICTATE = "dictate"           # Just type what I say
    INSTRUCT = "instruct"         # Transform/generate text based on instruction
    EDIT = "edit"                 # Modify the last output
    META = "meta"                 # Undo, read back, start over, etc.
    CONVERSATION = "conversation" # Multi-turn: content + instruction mixed


@dataclass
class Turn:
    """A single turn in the conversation."""
    text: str
    intent: Intent
    timestamp: datetime = field(default_factory=datetime.now)
    is_user: bool = True


@dataclass
class ConversationState:
    """Tracks the full conversation context."""
    turns: list[Turn] = field(default_factory=list)
    current_draft: str = ""         # The latest generated/dictated text
    draft_history: list[str] = field(default_factory=list)  # For undo
    active_context: str = "generic"  # email, chat, code, etc.

    def add_turn(self, text: str, intent: Intent, is_user: bool = True) -> None:
        self.turns.append(Turn(text=text, intent=intent, is_user=is_user))

    def push_draft(self, text: str) -> None:
        if self.current_draft:
            self.draft_history.append(self.current_draft)
        self.current_draft = text

    def undo_draft(self) -> Optional[str]:
        if self.draft_history:
            self.current_draft = self.draft_history.pop()
            return self.current_draft
        return None

    def clear(self) -> None:
        self.turns.clear()
        self.current_draft = ""
        self.draft_history.clear()

    @property
    def conversation_summary(self) -> str:
        """Build a summary of the conversation for LLM context."""
        parts = []
        for turn in self.turns[-10:]:  # Last 10 turns for context window
            role = "User" if turn.is_user else "Assistant"
            parts.append(f"{role}: {turn.text}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Instruction pattern matching (fast local detection before LLM)
# ---------------------------------------------------------------------------

_INSTRUCTION_PATTERNS: list[tuple[str, str, dict]] = [
    # (regex_pattern, action_name, extra_params)
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?(?:formal|professional)\s*(?:letter|email|message)?", "make_formal", {}),
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?(?:casual|informal)\s*(?:message|text)?", "make_casual", {}),
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?(?:claude\s*code|claude)\s+(?:master\s+)?prompt", "make_prompt", {}),
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?prompt", "make_prompt", {}),
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?(?:bullet|bulleted)\s*(?:points?|list)?", "make_bullets", {}),
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?(?:numbered|ordered)\s*list", "make_numbered", {}),
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?(?:email|mail)", "make_email", {}),
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?(?:code\s*comment|docstring)", "make_code_comment", {}),
    (r"(?:make|turn|convert)\s+(?:it|this|that)\s+(?:into\s+)?(?:a\s+)?(?:tweet|post|social\s*media)", "make_social", {}),
    (r"(?:make|turn)\s+(?:it|this|that)\s+(?:shorter|more\s+concise|brief)", "make_shorter", {}),
    (r"(?:make|turn)\s+(?:it|this|that)\s+(?:longer|more\s+detailed|elaborate)", "make_longer", {}),
    (r"(?:fix|correct)\s+(?:the\s+)?grammar", "fix_grammar", {}),
    (r"(?:summarize|summarise)\s+(?:it|this|that)", "summarize", {}),
    (r"translate\s+(?:it|this|that)?\s*(?:to|into)\s+(\w+)", "translate", {}),
    (r"replace\s+(.+?)\s+with\s+(.+)", "replace", {}),
    (r"(?:remove|delete)\s+(?:the\s+)?(.+)", "remove", {}),
    (r"(?:add|insert)\s+(.+?)\s+(?:at\s+the\s+)?(?:beginning|start|end|top|bottom)", "insert", {}),
    (r"(?:now\s+)?(?:send|type|paste|output|write)\s+(?:it|this|that)", "output", {}),
    (r"(?:read|say)\s+(?:it|that)\s+back", "read_back", {}),
    (r"start\s+over|clear|reset|new\s+(?:text|draft)", "clear", {}),
    (r"^undo$|^go\s+back$|^revert$", "undo", {}),
    (r"wake up.+daddy.+home|good morning trevo|hey trevo|hello trevo", "morning_briefing", {}),
]

_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), a, e) for p, a, e in _INSTRUCTION_PATTERNS]


def detect_intent_local(text: str) -> tuple[Intent, str, dict]:
    """Fast local intent detection using regex patterns.

    Returns (intent, action, params).
    """
    text_stripped = text.strip()

    # Check wake/activation phrases
    if re.match(r"(?:wake up.+daddy.+home|good morning trevo|hey trevo|hello trevo)", text_stripped, re.IGNORECASE):
        return Intent.META, "morning_briefing", {}

    # Check meta commands first
    if text_stripped.lower() in ("undo", "go back", "revert"):
        return Intent.META, "undo", {}
    if text_stripped.lower() in ("start over", "clear", "reset"):
        return Intent.META, "clear", {}
    if re.match(r"(?:read|say)\s+(?:it|that)\s+back", text_stripped, re.IGNORECASE):
        return Intent.META, "read_back", {}

    # Check instruction patterns
    for pattern, action, extra in _COMPILED_PATTERNS:
        match = pattern.search(text_stripped)
        if match:
            params = dict(extra)
            # Extract capture groups if any
            if match.groups():
                params["captures"] = list(match.groups())
            return Intent.INSTRUCT, action, params

    # Check if text ENDS with an instruction (content + instruction mixed)
    # Pattern: user says content, then says "now make it..."
    for trigger in ["now ", "and ", "then ", "ok ", "okay ", "alright "]:
        if trigger in text_stripped.lower():
            # Split at the trigger point and check if the tail is an instruction
            parts = text_stripped.lower().split(trigger, 1)
            if len(parts) == 2:
                tail = parts[1]
                for pattern, action, extra in _COMPILED_PATTERNS:
                    if pattern.search(tail):
                        params = dict(extra)
                        params["content"] = text_stripped[:text_stripped.lower().index(trigger)].strip()
                        return Intent.CONVERSATION, action, params

    # Default: it's dictation content
    return Intent.DICTATE, "dictate", {}


# ---------------------------------------------------------------------------
# Conversation Engine
# ---------------------------------------------------------------------------

class ConversationEngine:
    """The brain of trevo — understands conversation context and intent.

    Supports three LLM backends (all optional — works without any API key
    using Ollama locally):

    1. Ollama (local, free, recommended) — requires Ollama installed
    2. OpenAI (cloud, paid)
    3. Anthropic (cloud, paid)
    """

    def __init__(
        self,
        provider: str = "ollama",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        ollama_url: str = "http://localhost:11434",
    ) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.ollama_url = ollama_url

        # Default models per provider
        _defaults = {
            "ollama": "llama3.2",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-20241022",
            "groq": "llama-3.3-70b-versatile",    # Free tier: 30 req/min
            "gemini": "gemini-2.0-flash",           # Free tier: 15 req/min
        }
        self.model = model or _defaults.get(self.provider, "llama3.2")

        self.state = ConversationState()

        logger.info(
            "ConversationEngine initialised (provider={}, model={})",
            self.provider, self.model,
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_speech(
        self,
        raw_text: str,
        app_context: str = "generic",
    ) -> ConversationResult:
        """Process a speech utterance and return the appropriate action.

        This is the main method — call it with raw STT output and it figures
        out what to do.

        Returns a ConversationResult with:
        - action: what to do (inject_text, replace_text, read_back, etc.)
        - text: the text to inject/display
        - intent: the detected intent
        """
        if not raw_text or not raw_text.strip():
            return ConversationResult(action="noop", text="", intent=Intent.DICTATE)

        text = raw_text.strip()
        self.state.active_context = app_context

        # Step 1: Local intent detection (fast, no LLM needed)
        intent, action, params = detect_intent_local(text)

        logger.info("Intent: {} / Action: {} / Params: {}", intent.value, action, params)

        # Step 2: Route based on intent
        if intent == Intent.DICTATE:
            return await self._handle_dictation(text)

        elif intent == Intent.META:
            return self._handle_meta(action)

        elif intent == Intent.INSTRUCT:
            return await self._handle_instruction(text, action, params)

        elif intent == Intent.CONVERSATION:
            return await self._handle_conversation(text, action, params)

        return ConversationResult(action="inject_text", text=text, intent=intent)

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_dictation(self, text: str) -> ConversationResult:
        """User is just dictating content — clean it up and inject."""
        # Add to conversation history
        self.state.add_turn(text, Intent.DICTATE)

        # Clean up the text (basic filler removal)
        from utils.text_utils import remove_filler_words
        cleaned = remove_filler_words(text)

        # If we have an LLM available, do light polishing
        try:
            polished = await self._polish_text(cleaned)
        except Exception:
            polished = cleaned

        self.state.push_draft(polished)

        return ConversationResult(
            action="inject_text",
            text=polished,
            intent=Intent.DICTATE,
        )

    def _handle_meta(self, action: str) -> ConversationResult:
        """Handle meta commands like undo, clear, read back."""
        if action == "undo":
            previous = self.state.undo_draft()
            if previous is not None:
                return ConversationResult(
                    action="replace_all",
                    text=previous,
                    intent=Intent.META,
                    message="Reverted to previous version",
                )
            return ConversationResult(
                action="noop",
                text="",
                intent=Intent.META,
                message="Nothing to undo",
            )

        elif action == "clear":
            self.state.clear()
            return ConversationResult(
                action="clear",
                text="",
                intent=Intent.META,
                message="Cleared — starting fresh",
            )

        elif action == "read_back":
            return ConversationResult(
                action="read_back",
                text=self.state.current_draft,
                intent=Intent.META,
                message=self.state.current_draft or "No draft to read back",
            )

        return ConversationResult(action="noop", text="", intent=Intent.META)

    async def _handle_instruction(
        self, text: str, action: str, params: dict
    ) -> ConversationResult:
        """Handle transformation instructions on the current draft.

        e.g. "make it a formal letter", "translate to Spanish"
        """
        self.state.add_turn(text, Intent.INSTRUCT)
        draft = self.state.current_draft

        if not draft:
            return ConversationResult(
                action="noop",
                text="",
                intent=Intent.INSTRUCT,
                message="No text to transform — dictate something first",
            )

        # Special case: replace
        if action == "replace" and params.get("captures"):
            captures = params["captures"]
            if len(captures) >= 2:
                old, new = captures[0], captures[1]
                result = draft.replace(old, new)
                self.state.push_draft(result)
                return ConversationResult(
                    action="replace_all",
                    text=result,
                    intent=Intent.EDIT,
                    message=f"Replaced '{old}' with '{new}'",
                )

        # Special case: remove
        if action == "remove" and params.get("captures"):
            to_remove = params["captures"][0]
            result = draft.replace(to_remove, "").strip()
            result = re.sub(r"\s{2,}", " ", result)
            self.state.push_draft(result)
            return ConversationResult(
                action="replace_all",
                text=result,
                intent=Intent.EDIT,
                message=f"Removed '{to_remove}'",
            )

        # For all other instructions, use the LLM
        transformed = await self._transform_text(draft, action, params)
        self.state.push_draft(transformed)

        return ConversationResult(
            action="replace_all",
            text=transformed,
            intent=Intent.INSTRUCT,
            message=f"Applied: {action}",
        )

    async def _handle_conversation(
        self, text: str, action: str, params: dict
    ) -> ConversationResult:
        """Handle mixed content + instruction in a single utterance.

        e.g. "The quarterly results were great, now make it a formal report"
        """
        content = params.get("content", "")
        self.state.add_turn(text, Intent.CONVERSATION)

        if content:
            # First, process the content part
            from utils.text_utils import remove_filler_words
            cleaned_content = remove_filler_words(content)

            try:
                polished_content = await self._polish_text(cleaned_content)
            except Exception:
                polished_content = cleaned_content

            self.state.push_draft(polished_content)

        # Then apply the instruction
        draft = self.state.current_draft
        if not draft:
            return ConversationResult(
                action="noop",
                text="",
                intent=Intent.CONVERSATION,
                message="No content to transform",
            )

        transformed = await self._transform_text(draft, action, params)
        self.state.push_draft(transformed)

        return ConversationResult(
            action="inject_text",
            text=transformed,
            intent=Intent.CONVERSATION,
            message=f"Content processed and transformed: {action}",
        )

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _polish_text(self, text: str) -> str:
        """Light polishing — fix grammar, remove fillers."""
        prompt = (
            "Clean up this dictated text. Fix grammar, remove filler words "
            "(um, uh, like, you know), handle self-corrections, and produce "
            "clean readable text. Preserve the speaker's meaning exactly. "
            "Return ONLY the cleaned text.\n\n"
            f"Text: {text}"
        )
        return await self._call_llm(prompt)

    async def _transform_text(
        self, text: str, action: str, params: dict
    ) -> str:
        """Transform text based on the detected action."""

        # Build action-specific prompts
        prompts = {
            "make_formal": (
                "Rewrite the following text as a formal, professional piece of writing. "
                "Maintain all the original information and meaning. Add appropriate "
                "greetings/closings if it's a letter or email.\n\n"
                f"Text:\n{text}"
            ),
            "make_casual": (
                "Rewrite the following text in a casual, friendly tone. "
                "Keep all the information but make it sound natural and conversational.\n\n"
                f"Text:\n{text}"
            ),
            "make_prompt": (
                "Transform the following text into a well-structured prompt/instruction "
                "for an AI assistant (like Claude Code). Make it clear, specific, and "
                "actionable. Use proper formatting (headers, bullets, code blocks) where "
                "appropriate. Preserve all technical details and requirements.\n\n"
                f"Text:\n{text}"
            ),
            "make_bullets": (
                "Convert the following text into a well-organized bulleted list. "
                "Each bullet should be a clear, concise point.\n\n"
                f"Text:\n{text}"
            ),
            "make_numbered": (
                "Convert the following text into a numbered list. "
                "Each item should be a clear, concise point.\n\n"
                f"Text:\n{text}"
            ),
            "make_email": (
                "Rewrite the following text as a professional email. Include an "
                "appropriate subject line suggestion, greeting, body, and closing.\n\n"
                f"Text:\n{text}"
            ),
            "make_code_comment": (
                "Convert the following text into well-formatted code comments or "
                "documentation. Use proper comment syntax and be concise but thorough.\n\n"
                f"Text:\n{text}"
            ),
            "make_social": (
                "Rewrite the following as a concise, engaging social media post. "
                "Keep it under 280 characters if possible. Make it punchy.\n\n"
                f"Text:\n{text}"
            ),
            "make_shorter": (
                "Make the following text shorter and more concise while preserving "
                "all key information.\n\n"
                f"Text:\n{text}"
            ),
            "make_longer": (
                "Expand the following text with more detail and elaboration while "
                "maintaining the same tone and intent.\n\n"
                f"Text:\n{text}"
            ),
            "fix_grammar": (
                "Fix all grammar, spelling, and punctuation errors in the following "
                "text. Do not change the meaning or tone.\n\n"
                f"Text:\n{text}"
            ),
            "summarize": (
                "Summarize the following text concisely, capturing the key points.\n\n"
                f"Text:\n{text}"
            ),
        }

        # Handle translate with language parameter
        if action == "translate":
            target_lang = "English"
            if params.get("captures"):
                target_lang = params["captures"][0]
            prompt = (
                f"Translate the following text into {target_lang}. "
                "Maintain the tone and meaning.\n\n"
                f"Text:\n{text}"
            )
        else:
            prompt = prompts.get(action)

        if not prompt:
            # Fallback: use the raw instruction text as the prompt
            prompt = (
                f"Apply the following instruction to the text below.\n\n"
                f"Instruction: {action}\n\n"
                f"Text:\n{text}"
            )

        # Add conversation context if we have prior turns
        if len(self.state.turns) > 1:
            context = self.state.conversation_summary
            prompt = (
                f"Conversation context (for reference):\n{context}\n\n"
                f"---\n\n{prompt}"
            )

        prompt += "\n\nReturn ONLY the resulting text, no commentary or explanation."

        return await self._call_llm(prompt)

    async def _call_llm(self, prompt: str) -> str:
        """Route to the configured LLM provider."""
        if self.provider == "ollama":
            return await self._call_ollama(prompt)
        elif self.provider == "openai":
            return await self._call_openai(prompt)
        elif self.provider == "anthropic":
            return await self._call_anthropic(prompt)
        elif self.provider == "groq":
            return await self._call_groq(prompt)
        elif self.provider == "gemini":
            return await self._call_gemini(prompt)
        else:
            # No LLM available — return text as-is
            logger.warning("No LLM provider configured — returning raw text")
            return prompt.split("Text:\n")[-1].split("\n\nReturn ONLY")[0]

    async def _call_ollama(self, prompt: str) -> str:
        """Call local Ollama instance."""
        import httpx

        url = f"{self.ollama_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 4096},
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()["response"].strip()
        except httpx.ConnectError:
            logger.error(
                "Cannot connect to Ollama at {}. "
                "Install from https://ollama.com and run: ollama pull {}",
                self.ollama_url, self.model,
            )
            raise RuntimeError(
                f"Ollama not running at {self.ollama_url}. "
                f"Start it with: ollama serve"
            )
        except Exception:
            logger.exception("Ollama call failed")
            raise

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        from core.text_polisher import _get_openai_client

        client = _get_openai_client(self.api_key or "")
        response = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
        )
        return response.choices[0].message.content.strip()

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API."""
        from core.text_polisher import _get_anthropic_client

        client = _get_anthropic_client(self.api_key or "")
        response = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.content[0].text.strip()

    async def _call_groq(self, prompt: str) -> str:
        """Call Groq API (OpenAI-compatible, free tier available).

        Groq provides blazing-fast inference with free tier:
        - llama-3.3-70b-versatile: 30 req/min, 6000 tokens/min free
        - Sign up at: https://console.groq.com

        Uses the OpenAI SDK with a custom base_url.
        """
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package needed for Groq. Run: pip install openai")

        client = openai.AsyncOpenAI(
            api_key=self.api_key or "",
            base_url="https://api.groq.com/openai/v1",
        )
        response = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
        )
        return response.choices[0].message.content.strip()

    async def _call_gemini(self, prompt: str) -> str:
        """Call Google Gemini API (free tier: 15 req/min).

        Sign up at: https://aistudio.google.com/apikey
        Free tier includes gemini-2.0-flash with generous limits.
        """
        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key or ""}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096,
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            # Extract text from Gemini response
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            return ""

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear conversation state."""
        self.state.clear()
        logger.info("Conversation state cleared")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ConversationResult:
    """Result from processing a speech utterance.

    Attributes
    ----------
    action : str
        What to do:
        - "inject_text": paste text into active field
        - "replace_all": select all + paste (replaces current content)
        - "read_back": show text to user (TTS in future)
        - "clear": clear the current draft
        - "noop": do nothing
    text : str
        The text content for the action.
    intent : Intent
        The detected intent.
    message : str
        Human-readable status message for the UI.
    """
    action: str = "noop"
    text: str = ""
    intent: Intent = Intent.DICTATE
    message: str = ""
