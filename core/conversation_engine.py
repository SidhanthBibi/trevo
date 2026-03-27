"""Conversational AI engine for trevo.

This is the brain of trevo. Every utterance goes through the LLM which:
1. Understands context (what app you're in, what you've said before)
2. Detects intent naturally (no rigid regex — "forget the previous line" just works)
3. Produces the right output (cleaned text, transformation, or action)

The LLM sees the full conversation history and current draft, so it can handle
complex instructions like "add a bullet point", "next point", "delete that last
sentence", "make it sound more professional" — all in natural language.

Fast regex patterns still handle trivial meta commands (undo, clear) to save
an API call when the intent is unambiguous.
"""

from __future__ import annotations

import json
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
    INSTRUCT = "instruct"         # Transform/edit/act on text
    META = "meta"                 # Undo, read back, start over
    DESKTOP = "desktop"           # Open app, check mail, system command
    CONVERSATION = "conversation" # Trevo Mode back-and-forth chat


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
    current_draft: str = ""
    draft_history: list[str] = field(default_factory=list)
    active_context: str = "generic"

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
        parts = []
        for turn in self.turns[-10:]:
            role = "User" if turn.is_user else "Assistant"
            parts.append(f"{role}: {turn.text}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Fast local detection for unambiguous meta commands (saves an API call)
# ---------------------------------------------------------------------------

def _detect_fast_meta(text: str) -> Optional[str]:
    """Return action name if text is an unambiguous meta command, else None."""
    t = text.strip().lower()
    if t in ("undo", "go back", "revert"):
        return "undo"
    if t in ("start over", "clear", "reset", "new draft"):
        return "clear"
    if re.match(r"^(?:read|say)\s+(?:it|that)\s+back$", t):
        return "read_back"
    if re.match(r"^(?:wake up.+daddy.+home|good morning trevo|hey trevo|hello trevo)$", t):
        return "morning_briefing"
    return None


# ---------------------------------------------------------------------------
# System prompt for the LLM brain
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the brain of Trevo, a voice-to-text desktop assistant. The user speaks into \
their microphone and you receive their transcribed speech. Your job is to understand \
what they want and respond with a JSON action.

## Context
- App context: {app_context}
- Current draft (what was last typed): {current_draft}
- Conversation history:
{history}

## Rules
1. If the user is DICTATING content (they want text typed), clean up filler words \
(um, uh, like, you know), fix grammar, handle self-corrections, and output the \
polished text. Preserve their meaning exactly.

2. If the user gives an INSTRUCTION about their text (e.g. "forget the previous line", \
"add a bullet point", "next point", "make it formal", "delete that", "change the \
tone"), apply the instruction to the current draft and output the modified text.

3. If the user's speech MIXES content and instructions (e.g. "The quarterly results \
were great, now make it a formal email"), process both: add the content to the draft, \
then apply the instruction.

4. For desktop commands (e.g. "open Chrome", "check my email", "what's the weather"), \
respond with action "desktop_command".

5. For conversational queries in Trevo Mode (e.g. "what do you think about...", \
"tell me a joke"), respond with action "conversation".

## Response Format
ALWAYS respond with valid JSON only, no other text:
{{
  "action": "inject_text" | "replace_all" | "desktop_command" | "conversation" | "noop",
  "text": "the output text to type/display",
  "intent": "dictate" | "instruct" | "desktop" | "conversation",
  "message": "optional short status message for the UI",
  "voice_response": "optional text to speak aloud via TTS (for Trevo Mode)"
}}

Action meanings:
- "inject_text": Append/type this text at the cursor position
- "replace_all": Replace the entire current draft with this new text
- "desktop_command": Execute a desktop action (text field contains the command description)
- "conversation": Conversational response (text is empty, voice_response has the reply)
- "noop": Do nothing

CRITICAL: Return ONLY the JSON object. No markdown, no explanation, no code fences."""


# ---------------------------------------------------------------------------
# Conversation Engine
# ---------------------------------------------------------------------------

class ConversationEngine:
    """The brain of trevo — LLM-powered intent detection and text processing."""

    def __init__(
        self,
        provider: str = "ollama",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        ollama_url: str = "http://localhost:11434",
        snippets: Optional[dict[str, str]] = None,
    ) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.ollama_url = ollama_url
        self._snippets: dict[str, str] = snippets or {}

        _defaults = {
            "ollama": "llama3.2",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-20241022",
            "groq": "llama-3.3-70b-versatile",
            "gemini": "gemini-2.0-flash",
        }
        self.model = model or _defaults.get(self.provider, "llama3.2")
        self.state = ConversationState()
        self._trevo_mode = False  # True when JARVIS sphere is active

        logger.info(
            "ConversationEngine initialised (provider={}, model={})",
            self.provider, self.model,
        )

    @property
    def trevo_mode(self) -> bool:
        return self._trevo_mode

    @trevo_mode.setter
    def trevo_mode(self, value: bool) -> None:
        self._trevo_mode = value

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_speech(
        self,
        raw_text: str,
        app_context: str = "generic",
    ) -> ConversationResult:
        """Process a speech utterance through the LLM brain."""
        if not raw_text or not raw_text.strip():
            return ConversationResult(action="noop", text="", intent=Intent.DICTATE)

        text = raw_text.strip()
        self.state.active_context = app_context

        # Fast path: unambiguous meta commands (no LLM call needed)
        fast_action = _detect_fast_meta(text)
        if fast_action:
            return self._handle_meta(fast_action)

        # Everything else goes through the LLM
        try:
            result = await self._process_with_llm(text)
            return result
        except Exception as exc:
            logger.error(
                "LLM processing failed ({}: {}) — falling back to raw inject. "
                "Check your API key in Settings → AI Polishing.",
                type(exc).__name__, exc,
            )
            # Fallback: just inject the raw text
            self.state.add_turn(text, Intent.DICTATE)
            self.state.push_draft(text)
            return ConversationResult(
                action="inject_text", text=text, intent=Intent.DICTATE,
                message=f"⚠ LLM unavailable ({type(exc).__name__}), raw text injected",
            )

    async def _process_with_llm(self, text: str) -> ConversationResult:
        """Send the utterance to the LLM with full context."""
        history = self.state.conversation_summary or "(no prior conversation)"
        draft = self.state.current_draft or "(no current draft)"

        system = _SYSTEM_PROMPT.format(
            app_context=self.state.active_context,
            current_draft=draft,
            history=history,
        )

        # Inject user's personal snippets so the LLM can auto-fill them
        if self._snippets:
            snippet_lines = "\n".join(
                f"- {k.replace('_', ' ')}: {v}" for k, v in self._snippets.items() if v
            )
            if snippet_lines:
                system += (
                    "\n\n## User's Personal Info / Snippets\n"
                    "CRITICAL: When the user says ANY of these trigger phrases, you MUST "
                    "replace them with the exact values below — never type the phrase literally.\n"
                    f"{snippet_lines}\n\n"
                    "Trigger rules:\n"
                    "- 'my phone number' / 'my number' / 'call me at' → use the phone value\n"
                    "- 'my name' / 'my name is' / 'I am' → use the name value\n"
                    "- 'my email' / 'email me at' / 'my email address' → use the email value\n"
                    "- Generic mentions (e.g. 'a phone number') stay as literal text\n"
                    "- Only replace when the user clearly refers to THEIR OWN info with 'my' / 'I'"
                )

        # In Trevo Mode, bias toward conversation with voice responses
        if self._trevo_mode:
            system += (
                "\n\n## TREVO MODE ACTIVE\n"
                "You are in Trevo Mode (JARVIS-like voice assistant). "
                "ALWAYS include a natural voice_response field — speak back to the user. "
                "For dictation, confirm what you typed (e.g. \"Got it, I've typed that for you.\"). "
                "For instructions, confirm the action (e.g. \"Done, I've made it more formal.\"). "
                "For conversation, respond naturally and helpfully. "
                "For desktop commands, confirm what you're doing (e.g. \"Opening Chrome for you.\"). "
                "Keep voice_response concise and natural — like a real assistant speaking."
            )

        user_msg = f"User said: {text}"

        raw_response = await self._call_llm_chat(system, user_msg)

        # Parse the JSON response
        result = self._parse_llm_response(raw_response, text)

        # Update conversation state
        intent = Intent(result.intent.value) if isinstance(result.intent, Intent) else Intent.DICTATE
        self.state.add_turn(text, intent)

        if result.action in ("inject_text", "replace_all") and result.text:
            self.state.push_draft(result.text)

        return result

    def _parse_llm_response(self, raw: str, original_text: str) -> ConversationResult:
        """Parse JSON response from the LLM, with robust fallback."""
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove ```json\n...\n```
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # LLM didn't return valid JSON — treat response as polished text
            logger.warning("LLM returned non-JSON response, using as polished text")
            fallback_text = cleaned if cleaned else original_text
            return ConversationResult(
                action="inject_text",
                text=self._expand_snippets(fallback_text),
                intent=Intent.DICTATE,
            )

        action = data.get("action", "inject_text")
        text = data.get("text", "")
        intent_str = data.get("intent", "dictate")
        message = data.get("message", "")
        voice = data.get("voice_response", "")

        # Map intent string to enum
        try:
            intent = Intent(intent_str)
        except ValueError:
            intent = Intent.DICTATE

        return ConversationResult(
            action=action,
            text=self._expand_snippets(text) if text else text,
            intent=intent,
            message=message,
            voice_response=voice,
        )

    # ------------------------------------------------------------------
    # Snippet post-processing (regex fallback for LLM misses)
    # ------------------------------------------------------------------

    def _expand_snippets(self, text: str) -> str:
        """Replace 'my phone number', 'my name', etc. with actual snippet values."""
        if not self._snippets or not text:
            return text

        _TRIGGER_PATTERNS: dict[str, list[str]] = {
            "my_name": [r"\bmy name\b", r"\bmy full name\b"],
            "my_phone": [r"\bmy (?:phone )?number\b", r"\bmy phone\b",
                         r"\bcall me at\b"],
            "my_email": [r"\bmy email(?:\s+address)?\b", r"\bemail me at\b"],
        }

        for key, patterns in _TRIGGER_PATTERNS.items():
            value = self._snippets.get(key, "")
            if not value:
                continue
            for pattern in patterns:
                text = re.sub(pattern, value, text, flags=re.IGNORECASE)

        return text

    # ------------------------------------------------------------------
    # Meta commands (handled locally, no LLM)
    # ------------------------------------------------------------------

    def _handle_meta(self, action: str) -> ConversationResult:
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
                action="noop", text="", intent=Intent.META,
                message="Nothing to undo",
            )

        if action == "clear":
            self.state.clear()
            return ConversationResult(
                action="clear", text="", intent=Intent.META,
                message="Cleared — starting fresh",
            )

        if action == "read_back":
            return ConversationResult(
                action="read_back",
                text=self.state.current_draft,
                intent=Intent.META,
                message=self.state.current_draft or "No draft to read back",
                voice_response=self.state.current_draft or "No draft to read back",
            )

        if action == "morning_briefing":
            return ConversationResult(
                action="morning_briefing", text="", intent=Intent.META,
                message="Starting morning briefing",
                voice_response="Good morning! Let me get your briefing ready.",
            )

        return ConversationResult(action="noop", text="", intent=Intent.META)

    # ------------------------------------------------------------------
    # LLM chat call (system + user message)
    # ------------------------------------------------------------------

    async def _call_llm_chat(self, system: str, user_msg: str) -> str:
        """Call LLM with system + user message pair."""
        if self.provider == "groq":
            return await self._chat_groq(system, user_msg)
        elif self.provider == "gemini":
            return await self._chat_gemini(system, user_msg)
        elif self.provider == "openai":
            return await self._chat_openai(system, user_msg)
        elif self.provider == "anthropic":
            return await self._chat_anthropic(system, user_msg)
        elif self.provider == "ollama":
            return await self._chat_ollama(system, user_msg)
        else:
            logger.warning("Unknown LLM provider '{}' — returning raw text", self.provider)
            return user_msg

    async def _chat_groq(self, system: str, user_msg: str) -> str:
        """Groq API — free tier: 30 req/min."""
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package needed for Groq. Run: pip install openai")

        if not self.api_key:
            logger.error("Groq API key is empty/missing — LLM will fail")
            raise RuntimeError("Groq API key not configured. Set it in Settings → AI Polishing.")

        logger.debug("Calling Groq API (model={}, key={}...)", self.model, self.api_key[:8] if self.api_key else "NONE")

        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            result = response.choices[0].message.content.strip()
            logger.debug("Groq response: {}", result[:200])
            return result
        except Exception as exc:
            logger.error("Groq API call failed: {} — {}", type(exc).__name__, exc)
            raise

    async def _chat_gemini(self, system: str, user_msg: str) -> str:
        """Google Gemini API — free tier: 15 req/min."""
        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user_msg}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url, json=payload,
                headers={"Content-Type": "application/json"},
                params={"key": self.api_key or ""},
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            return ""

    async def _chat_openai(self, system: str, user_msg: str) -> str:
        """OpenAI API."""
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package needed. Run: pip install openai")

        client = openai.AsyncOpenAI(api_key=self.api_key or "")
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content.strip()

    async def _chat_anthropic(self, system: str, user_msg: str) -> str:
        """Anthropic Claude API."""
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package needed. Run: pip install anthropic")

        client = anthropic.AsyncAnthropic(api_key=self.api_key or "")
        response = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.2,
        )
        return response.content[0].text.strip()

    async def _chat_ollama(self, system: str, user_msg: str) -> str:
        """Local Ollama instance."""
        import httpx

        url = f"{self.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 4096},
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()["message"]["content"].strip()
        except Exception:
            logger.exception("Ollama call failed")
            raise

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
    """Result from processing a speech utterance."""
    action: str = "noop"
    text: str = ""
    intent: Intent = Intent.DICTATE
    message: str = ""
    voice_response: str = ""  # Text to speak via TTS (Trevo Mode)
