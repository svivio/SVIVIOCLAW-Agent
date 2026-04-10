"""
SVIVIOCLAW — Multi-provider AI backend
Supports: Anthropic (Claude), OpenRouter (any model), Ollama (local)
"""

import json
import base64
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Optional
from io import BytesIO


# ── Action result format shared by all providers ──────────────────────────────

class AgentResponse:
    """Normalised response from any provider."""
    def __init__(
        self,
        text: str = "",
        thinking: str = "",
        actions: list[dict] = None,     # list of computer-use action dicts
        done: bool = False,
        raw: Any = None,
    ):
        self.text    = text
        self.thinking = thinking
        self.actions  = actions or []
        self.done     = done
        self.raw      = raw


# ── Base provider ─────────────────────────────────────────────────────────────

class BaseProvider(ABC):
    """Abstract AI backend that powers SVIVIOCLAW's agent loop."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        system: str,
        screen_w: int,
        screen_h: int,
    ) -> AgentResponse:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


# ── Anthropic (Claude) ────────────────────────────────────────────────────────

class AnthropicProvider(BaseProvider):
    """
    Full Claude computer-use with native tool support.
    Best quality, requires ANTHROPIC_API_KEY.
    """

    TOOL_TYPE = "computer_20241022"
    BETA      = "computer-use-2024-10-22"
    MODEL_DEFAULT = "claude-opus-4-6"

    def __init__(self, api_key: str, model: str = ""):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model  = model or self.MODEL_DEFAULT

    @property
    def name(self) -> str:
        return f"Anthropic / {self._model}"

    def chat(self, messages, system, screen_w, screen_h) -> AgentResponse:
        tool = {
            "type": self.TOOL_TYPE,
            "name": "computer",
            "display_width_px": screen_w,
            "display_height_px": screen_h,
            "display_number": 1,
        }
        resp = self._client.beta.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            tools=[tool],
            messages=messages,
            thinking={"type": "adaptive"},
            betas=[self.BETA],
        )

        text, thinking, actions = "", "", []
        for block in resp.content:
            t = getattr(block, "type", None)
            if t == "thinking":
                thinking = block.thinking
            elif t == "text":
                text = block.text
            elif t == "tool_use" and block.name == "computer":
                actions.append({"id": block.id, "action": block.input})

        done = resp.stop_reason == "end_turn" and not actions
        return AgentResponse(text=text, thinking=thinking, actions=actions,
                             done=done, raw=resp)


# ── OpenRouter ────────────────────────────────────────────────────────────────

OPENROUTER_ACTION_SCHEMA = """\
You MUST respond with ONLY valid JSON — no markdown fences, no extra text.

Schema:
{
  "thinking": "<brief reasoning about what you see and what to do>",
  "text": "<your message to the user, if any>",
  "action": {
    "type": "screenshot|left_click|right_click|double_click|middle_click|type|key|scroll|mouse_move|left_click_drag|hold_key|done",
    "coordinate": [x, y],          // for click/move/scroll actions (integers)
    "start_coordinate": [x, y],    // for left_click_drag
    "end_coordinate": [x, y],      // for left_click_drag
    "text": "...",                  // for type action
    "key": "ctrl+c",               // for key action (e.g. ctrl+c, alt+tab, enter, win)
    "direction": "up|down|left|right", // for scroll
    "amount": 3,                    // for scroll (number of ticks)
    "duration": 1.0                 // for hold_key (seconds)
  },
  "done": false   // true ONLY when the task is 100% complete
}

If done is true, set action.type to "done" and explain in "text" what was accomplished.
"""

class OpenRouterProvider(BaseProvider):
    """
    Uses OpenRouter's OpenAI-compatible API.
    Works with any vision model: GPT-4o, Gemini, Claude (via OR), Llama-Vision, etc.
    """

    BASE_URL = "https://openrouter.ai/api/v1"
    MODEL_DEFAULT = "anthropic/claude-opus-4"

    def __init__(self, api_key: str, model: str = ""):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("pip install openai  (required for OpenRouter)")
        self._client = OpenAI(api_key=api_key, base_url=self.BASE_URL)
        self._model  = model or self.MODEL_DEFAULT

    @property
    def name(self) -> str:
        return f"OpenRouter / {self._model}"

    def chat(self, messages, system, screen_w, screen_h) -> AgentResponse:
        # Convert messages to OpenAI format
        oai_messages = [{"role": "system", "content": system + "\n\n" + OPENROUTER_ACTION_SCHEMA}]

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                oai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append({"type": "text", "text": block["text"]})
                        elif block.get("type") == "image":
                            src = block.get("source", {})
                            if src.get("type") == "base64":
                                parts.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{src['media_type']};base64,{src['data']}"
                                    }
                                })
                        elif block.get("type") == "tool_result":
                            # Flatten tool results into text + optional image
                            for sub in block.get("content", []):
                                if sub.get("type") == "text":
                                    parts.append({"type": "text", "text": sub["text"]})
                                elif sub.get("type") == "image":
                                    s = sub.get("source", {})
                                    if s.get("type") == "base64":
                                        parts.append({
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:{s['media_type']};base64,{s['data']}"
                                            }
                                        })
                if parts:
                    oai_messages.append({"role": role, "content": parts})

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=oai_messages,
            max_tokens=2048,
            temperature=0.2,
        )

        raw_text = resp.choices[0].message.content or ""
        return self._parse_json_response(raw_text, resp)

    def _parse_json_response(self, raw: str, resp_obj) -> AgentResponse:
        # Strip markdown fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: treat as plain text, take screenshot next
            return AgentResponse(
                text=raw,
                actions=[{"id": "fallback", "action": {"type": "screenshot"}}],
                done=False,
                raw=resp_obj,
            )

        action_dict = data.get("action", {})
        action_type = action_dict.get("type", "screenshot")
        done = bool(data.get("done", False)) or action_type == "done"

        actions = [] if done else [{"id": "or_action", "action": action_dict}]

        return AgentResponse(
            text=data.get("text", ""),
            thinking=data.get("thinking", ""),
            actions=actions,
            done=done,
            raw=resp_obj,
        )


# ── Ollama (local) ────────────────────────────────────────────────────────────

class OllamaProvider(BaseProvider):
    """
    Local AI via Ollama. Works offline — no API key needed.
    Recommended vision models: llama3.2-vision, llava, bakllava, minicpm-v
    """

    BASE_URL_DEFAULT = "http://localhost:11434"
    MODEL_DEFAULT    = "llama3.2-vision"

    def __init__(self, model: str = "", base_url: str = ""):
        self._model    = model or self.MODEL_DEFAULT
        self._base_url = (base_url or self.BASE_URL_DEFAULT).rstrip("/")

    @property
    def name(self) -> str:
        return f"Ollama / {self._model}"

    def chat(self, messages, system, screen_w, screen_h) -> AgentResponse:
        import urllib.request, urllib.error

        # Build the prompt for Ollama
        prompt_parts = [
            f"SYSTEM: {system}\n\n{OPENROUTER_ACTION_SCHEMA}\n\n"
        ]

        images_b64 = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if isinstance(content, str):
                prompt_parts.append(f"{role.upper()}: {content}\n")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            prompt_parts.append(f"{role.upper()}: {block['text']}\n")
                        elif block.get("type") == "image":
                            src = block.get("source", {})
                            if src.get("type") == "base64":
                                images_b64.append(src["data"])
                        elif block.get("type") == "tool_result":
                            for sub in block.get("content", []):
                                if sub.get("type") == "text":
                                    prompt_parts.append(f"RESULT: {sub['text']}\n")
                                elif sub.get("type") == "image":
                                    s = sub.get("source", {})
                                    if s.get("type") == "base64":
                                        images_b64.append(s["data"])

        prompt_parts.append("\nASSISTANT (JSON only):")
        full_prompt = "".join(prompt_parts)

        payload = json.dumps({
            "model": self._model,
            "prompt": full_prompt,
            "images": images_b64[-2:],  # Send last 2 screenshots max
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as f:
                result = json.loads(f.read())
            raw_text = result.get("response", "")
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot reach Ollama at {self._base_url}. "
                "Make sure Ollama is running: 'ollama serve'"
            ) from e

        # Reuse OpenRouter parser (same JSON schema)
        or_prov = OpenRouterProvider.__new__(OpenRouterProvider)
        return or_prov._parse_json_response(raw_text, result)


# ── Factory ───────────────────────────────────────────────────────────────────

def build_provider(
    backend: str,
    api_key: str = "",
    model: str = "",
    ollama_url: str = "",
) -> BaseProvider:
    """
    backend: "anthropic" | "openrouter" | "ollama"
    """
    b = backend.lower().strip()
    if b == "anthropic":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set.")
        return AnthropicProvider(api_key=key, model=model)

    elif b == "openrouter":
        key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not set.")
        return OpenRouterProvider(api_key=key, model=model)

    elif b == "ollama":
        return OllamaProvider(model=model, base_url=ollama_url)

    else:
        raise ValueError(f"Unknown backend: {backend!r}. Choose: anthropic | openrouter | ollama")
