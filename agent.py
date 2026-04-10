"""
SVIVIOCLAW — Core Agent Engine
Multi-provider: Anthropic (Claude) | OpenRouter | Ollama
Primary mission: autonomous Claude Code + Chrome project work.
"""

import os
import sys
import base64
import time
import logging
from io import BytesIO
from typing import Optional, Callable

from providers import BaseProvider, AgentResponse, build_provider
from memory import MemoryManager, get_memory

try:
    import pyautogui
    import PIL.ImageGrab
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.08
except ImportError:
    sys.exit("Run setup.bat first to install dependencies.")

logger = logging.getLogger("svivioclaw")


# ── Screen helpers ────────────────────────────────────────────────────────────

def screen_size() -> tuple[int, int]:
    return pyautogui.size()


def screenshot_b64() -> str:
    img = PIL.ImageGrab.grab()
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.standard_b64encode(buf.getvalue()).decode()


def image_block(b64: str) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}


# ── Action executor ───────────────────────────────────────────────────────────

def execute_action(action: dict) -> tuple[str, Optional[str]]:
    """
    Execute a computer-use action dict.
    Returns (description_str, optional_screenshot_b64).
    """
    t = action.get("type", "")
    try:
        if t == "screenshot":
            time.sleep(0.3)
            return "Screenshot captured.", screenshot_b64()

        elif t == "left_click":
            x, y = action["coordinate"]
            pyautogui.click(x, y)
            time.sleep(0.25)
            return f"Left-clicked ({x},{y}).", screenshot_b64()

        elif t == "right_click":
            x, y = action["coordinate"]
            pyautogui.rightClick(x, y)
            time.sleep(0.25)
            return f"Right-clicked ({x},{y}).", screenshot_b64()

        elif t == "middle_click":
            x, y = action["coordinate"]
            pyautogui.middleClick(x, y)
            time.sleep(0.25)
            return f"Middle-clicked ({x},{y}).", screenshot_b64()

        elif t == "double_click":
            x, y = action["coordinate"]
            pyautogui.doubleClick(x, y)
            time.sleep(0.25)
            return f"Double-clicked ({x},{y}).", screenshot_b64()

        elif t == "mouse_move":
            x, y = action["coordinate"]
            pyautogui.moveTo(x, y, duration=0.25)
            return f"Moved mouse to ({x},{y}).", None

        elif t == "left_click_drag":
            sx, sy = action["start_coordinate"]
            ex, ey = action["end_coordinate"]
            pyautogui.mouseDown(sx, sy)
            time.sleep(0.05)
            pyautogui.dragTo(ex, ey, duration=0.4)
            pyautogui.mouseUp()
            time.sleep(0.2)
            return f"Dragged ({sx},{sy})→({ex},{ey}).", screenshot_b64()

        elif t == "type":
            text = action["text"]
            pyautogui.typewrite(text, interval=0.03)
            time.sleep(0.15)
            return f"Typed: {text[:80]}{'…' if len(text) > 80 else ''}", screenshot_b64()

        elif t == "key":
            key = action["key"]
            parts = key.lower().replace(" ", "").split("+")
            if len(parts) > 1:
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(parts[0])
            time.sleep(0.2)
            return f"Key: {key}", screenshot_b64()

        elif t == "scroll":
            x, y = action["coordinate"]
            direction = action.get("direction", "down")
            amount = int(action.get("amount", 3))
            if direction == "down":   pyautogui.scroll(-amount, x=x, y=y)
            elif direction == "up":   pyautogui.scroll(amount, x=x, y=y)
            elif direction == "left": pyautogui.hscroll(-amount, x=x, y=y)
            elif direction == "right":pyautogui.hscroll(amount, x=x, y=y)
            time.sleep(0.2)
            return f"Scrolled {direction}×{amount} at ({x},{y}).", screenshot_b64()

        elif t == "cursor_position":
            pos = pyautogui.position()
            return f"Cursor at {pos}.", None

        elif t == "hold_key":
            key = action["key"]
            duration = float(action.get("duration", 1.0))
            pyautogui.keyDown(key)
            time.sleep(duration)
            pyautogui.keyUp(key)
            return f"Held '{key}' for {duration}s.", screenshot_b64()

        elif t == "done":
            return "Task complete.", None

        else:
            return f"Unknown action: {t}", None

    except Exception as exc:
        return f"ERROR in '{t}': {exc}", None


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are SVIVIOCLAW — an autonomous AI software engineering agent by Vivaan.io.

Your PRIMARY TOOLS are:
  • Claude Code (the desktop/CLI coding assistant) — for writing, editing, running code
  • Google Chrome — for web research, APIs, documentation, testing web apps
  • Windows Terminal / Command Prompt — for running commands, npm, pip, git, etc.

## Your Mission
Complete software development projects AUTONOMOUSLY end-to-end:
  - Plan the project → open Claude Code → delegate coding to Claude Code
  - Research in Chrome (MDN, GitHub, Stack Overflow, npm, PyPI, etc.)
  - Test and verify the output
  - Iterate until the project is fully done and working

## Workflow
1. Take a screenshot to see the current screen state.
2. If Claude Code is not open, launch it (taskbar, Start Menu, or Desktop).
3. Open Chrome alongside for research when needed.
4. Give Claude Code clear, detailed coding instructions.
5. Verify Claude Code's output — read code, run tests, check terminal output.
6. Switch between Chrome and Claude Code freely using Alt+Tab or the taskbar.
7. Keep working until the project is 100% complete and tested.

## AUTONOMY RULES — CRITICAL
- NEVER stop to ask the user for clarification. Make a decision and proceed.
- NEVER say "I need more info" — infer and act.
- NEVER stop early — keep going until done.
- If blocked, try 3 different approaches before moving on.
- Handle all errors yourself: read error → fix → retry.
- Use keyboard shortcuts heavily (Alt+Tab, Ctrl+C/V, Win key, etc.)
- Be PRECISE with pixel coordinates — use the actual visible UI elements.
- Click text fields before typing.
- After every action verify the result with a screenshot.
- Signal completion ONLY when the project is 100% done and working.

Screen resolution: {screen_w}×{screen_h} px.

App locations (Windows 11):
- Claude Code: taskbar, Start Menu search "Claude", or Desktop shortcut
- Chrome: taskbar, Start Menu search "Chrome", or Desktop shortcut
- Terminal: Win+X → Terminal, or search "cmd" in Start Menu

{memory_block}
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

class SVIVIOCLAWAgent:
    """
    Autonomous computer-use agent.
    Works with Anthropic, OpenRouter, or Ollama backends.
    """

    def __init__(
        self,
        provider: Optional[BaseProvider] = None,
        api_key: Optional[str] = None,
        max_iter: int = 200,
        on_event: Optional[Callable[[str, dict], None]] = None,
        backend: str = "anthropic",
        model: str = "",
        openrouter_key: str = "",
        ollama_url: str = "",
        memory: Optional[MemoryManager] = None,
        resume_task_id: Optional[int] = None,
    ):
        self.max_iter = max_iter
        self.on_event = on_event or (lambda evt, data: None)
        self.sw, self.sh = screen_size()
        self._messages: list[dict] = []
        self._iter = 0
        self._running = False
        self._task_id: Optional[int] = None
        self._mem: MemoryManager = memory or get_memory()
        self._resume_task_id = resume_task_id

        if provider is not None:
            self._provider = provider
        else:
            key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            if backend == "openrouter":
                key = openrouter_key or os.environ.get("OPENROUTER_API_KEY", key)
            self._provider = build_provider(
                backend=backend,
                api_key=key,
                model=model,
                ollama_url=ollama_url,
            )

        logger.info("SVIVIOCLAW ready | provider=%s | screen=%dx%d",
                    self._provider.name, self.sw, self.sh)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _system(self) -> str:
        return SYSTEM_PROMPT.format(
            screen_w=self.sw,
            screen_h=self.sh,
            memory_block=self._mem.context_block(),
        )

    def _emit(self, event: str, **data):
        self.on_event(event, data)

    def stop(self):
        self._running = False
        if self._task_id:
            self._mem.save_messages(self._task_id, self._messages)
            self._mem.interrupt_task(self._task_id, self._iter)

    # ── Anthropic-specific message building ───────────────────────────────────

    def _build_tool_result_content(self, desc: str, ss: Optional[str]) -> list[dict]:
        parts: list[dict] = [{"type": "text", "text": desc}]
        if ss:
            parts.append(image_block(ss))
        return parts

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self, task: str) -> str:
        self._running = True
        self._iter    = 0

        logger.info("Task: %s", task)
        self._emit("task_start", task=task)

        # ── Resume or fresh start ─────────────────────────────────────────
        if self._resume_task_id:
            saved = self._mem.load_messages(self._resume_task_id)
            if saved:
                self._messages = saved
                self._task_id  = self._resume_task_id
                self._mem.finish_task(self._task_id, "", 0, status="running")
                self._emit("memory_event", msg=f"Resuming task #{self._task_id} with {len(saved)} saved messages.")
                logger.info("Resuming task_id=%d (%d messages)", self._task_id, len(saved))
            else:
                self._resume_task_id = None

        if not self._resume_task_id:
            self._messages = []
            self._task_id = self._mem.start_task(task, provider=self._provider.name)
            init_ss = screenshot_b64()
            self._messages.append({
                "role": "user",
                "content": [
                    image_block(init_ss),
                    {"type": "text", "text": f"Complete this task autonomously: {task}"},
                ],
            })
            self._emit("screenshot", data=init_ss)

        final_text = "Task ended."

        while self._running and self._iter < self.max_iter:
            self._iter += 1
            logger.info("Iteration %d/%d  provider=%s", self._iter, self.max_iter,
                        self._provider.name)
            self._emit("iteration", n=self._iter, max=self.max_iter)

            try:
                response: AgentResponse = self._provider.chat(
                    messages=self._messages,
                    system=self._system(),
                    screen_w=self.sw,
                    screen_h=self.sh,
                )
            except ConnectionError as exc:
                logger.error("Connection error: %s", exc)
                self._emit("warning", msg=str(exc))
                break
            except Exception as exc:
                if "overload" in str(exc).lower():
                    logger.warning("Provider overloaded — waiting 30s")
                    self._emit("warning", msg="Provider overloaded, retrying in 30s…")
                    time.sleep(30)
                    continue
                raise

            # Emit events
            if response.thinking:
                self._emit("thinking", text=response.thinking)
            if response.text:
                logger.info("Agent: %s", response.text[:120])
                self._emit("message", text=response.text)
                final_text = response.text
                # Extract discoverable facts from the text
                self._mem.extract_and_learn(response.text, task_id=self._task_id)

            # Append assistant turn to history
            if hasattr(response.raw, "content"):
                self._messages.append({"role": "assistant", "content": response.raw.content})
            else:
                self._messages.append({
                    "role": "assistant",
                    "content": response.text or "(no text)"
                })

            # Checkpoint messages every 10 iterations (for resume)
            if self._task_id and self._iter % 10 == 0:
                self._mem.save_messages(self._task_id, self._messages)

            # Done?
            if response.done:
                self._mem.finish_task(self._task_id, final_text, self._iter)
                self._emit("done", text=final_text)
                break

            # No actions → done
            if not response.actions:
                self._mem.finish_task(self._task_id, final_text, self._iter)
                self._emit("done", text=final_text)
                break

            # Execute actions
            tool_results: list[dict] = []
            for entry in response.actions:
                action = entry["action"]
                action_id = entry.get("id", "act")
                action_type = action.get("type", "?")

                self._emit("action", action=action)
                logger.info("Action: %s %s", action_type, action)

                desc, ss = execute_action(action)
                logger.info("Result: %s", desc)
                self._emit("action_result", desc=desc, screenshot=ss)

                result_content = self._build_tool_result_content(desc, ss)
                if ss:
                    self._emit("screenshot", data=ss)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": action_id,
                    "content": result_content,
                })

            if tool_results:
                self._messages.append({"role": "user", "content": tool_results})

        if self._iter >= self.max_iter:
            final_text = f"Reached max iterations ({self.max_iter})."
            self._mem.finish_task(self._task_id, final_text, self._iter, status="failed")
            self._emit("done", text=final_text)

        self._running = False
        return final_text


# ── Backward compat alias ─────────────────────────────────────────────────────
GUIOCAgent = SVIVIOCLAWAgent
