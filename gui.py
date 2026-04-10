"""
GUIOC Desktop GUI — Claude Desktop-style native window
Modern dark UI with chat bubbles, live screen view, smooth animations.
"""

import os
import sys
import threading
import queue
import base64
from io import BytesIO
from datetime import datetime
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter
except ImportError:
    sys.exit("Run setup.bat first (needs Pillow).")

# ── Palette (Claude Desktop inspired) ─────────────────────────────────────────
C = {
    "bg":        "#1a1a2e",
    "sidebar":   "#16213e",
    "surface":   "#0f3460",
    "card":      "#1e1e3a",
    "input_bg":  "#252550",
    "border":    "#2d2d5e",
    "accent":    "#8b5cf6",   # violet
    "accent2":   "#06b6d4",   # cyan
    "text":      "#f0f0ff",
    "muted":     "#8888bb",
    "ok":        "#4ade80",
    "warn":      "#fb923c",
    "err":       "#f87171",
    "bubble_a":  "#2d2d60",   # agent bubble
    "bubble_t":  "#1a1a40",   # thinking bubble
    "bubble_u":  "#8b5cf6",   # user bubble
    "white":     "#ffffff",
}

event_queue: "queue.Queue[tuple[str, dict]]" = queue.Queue()

def on_event(event: str, data: dict):
    event_queue.put((event, data))


# ── Rounded rectangle helper ──────────────────────────────────────────────────

def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r=12, **kw):
    pts = [
        x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
        x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


# ── Chat message widget ───────────────────────────────────────────────────────

class ChatFeed(tk.Frame):
    """Scrollable chat bubble feed."""
    FONTS = {}

    def __init__(self, parent, **kw):
        kw.setdefault("bg", C["bg"])
        super().__init__(parent, **kw)

        # Canvas + scrollbar
        self._vsb = tk.Scrollbar(self, orient="vertical", width=8,
                                  troughcolor=C["bg"], bg=C["border"])
        self._vsb.pack(side="right", fill="y")

        self._canvas = tk.Canvas(self, bg=C["bg"], yscrollcommand=self._vsb.set,
                                  highlightthickness=0)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._vsb.configure(command=self._canvas.yview)

        self._inner = tk.Frame(self._canvas, bg=C["bg"])
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, _=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._win, width=e.width)

    def _on_mousewheel(self, e):
        self._canvas.yview_scroll(-1 * (e.delta // 120), "units")

    def _font(self, size=10, bold=False):
        key = (size, bold)
        if key not in self.FONTS:
            weight = "bold" if bold else "normal"
            self.FONTS[key] = tkfont.Font(family="Segoe UI", size=size, weight=weight)
        return self.FONTS[key]

    def add_bubble(self, text: str, role: str = "agent", tag: str = ""):
        """Add a styled chat bubble. role: agent|user|thinking|action|result|system"""
        outer = tk.Frame(self._inner, bg=C["bg"])
        outer.pack(fill="x", padx=12, pady=4)

        cfg = {
            "agent":    (C["bubble_a"], C["text"],   "▲ Claude",  "left"),
            "user":     (C["bubble_u"], C["white"],  "You",       "right"),
            "thinking": (C["bubble_t"], C["muted"],  "Thinking…", "left"),
            "action":   (C["card"],     C["accent"], "→ Action",  "left"),
            "result":   (C["card"],     C["ok"],     "✓ Result",  "left"),
            "system":   (C["bg"],       C["muted"],  "",          "center"),
        }.get(role, (C["bubble_a"], C["text"], "", "left"))

        bg, fg, label, align = cfg

        wrap_w = 460

        if align == "right":
            wrap = tk.Frame(outer, bg=C["bg"])
            wrap.pack(side="right")
        elif align == "center":
            lbl = tk.Label(outer, text=text, bg=C["bg"], fg=C["muted"],
                           font=self._font(8), wraplength=wrap_w)
            lbl.pack(fill="x", pady=2)
            self._scroll_bottom()
            return
        else:
            wrap = tk.Frame(outer, bg=C["bg"])
            wrap.pack(side="left")

        # Label row
        if label:
            tk.Label(wrap, text=label, bg=C["bg"], fg=C["accent"] if role == "agent" else fg,
                     font=self._font(8, bold=True)).pack(anchor="w", padx=4)

        bubble = tk.Frame(wrap, bg=bg, padx=14, pady=10)
        bubble.pack(fill="none", anchor="w" if align != "right" else "e")
        bubble.configure(highlightbackground=C["border"], highlightthickness=1)

        lbl = tk.Label(bubble, text=text, bg=bg, fg=fg,
                       font=self._font(9), wraplength=wrap_w,
                       justify="left", anchor="w")
        lbl.pack()

        self._scroll_bottom()

    def _scroll_bottom(self):
        self._inner.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._canvas.yview_moveto(1.0)

    def clear(self):
        for w in self._inner.winfo_children():
            w.destroy()


# ── Screen viewer ─────────────────────────────────────────────────────────────

class ScreenPanel(tk.Frame):
    def __init__(self, parent, **kw):
        kw.setdefault("bg", C["bg"])
        super().__init__(parent, **kw)

        lbl = tk.Label(self, text="  LIVE SCREEN", bg=C["bg"], fg=C["muted"],
                       font=("Segoe UI", 8, "bold"), anchor="w")
        lbl.pack(fill="x", pady=(8, 4))

        self._canvas = tk.Canvas(self, bg="#000", highlightthickness=1,
                                  highlightbackground=C["border"])
        self._canvas.pack(fill="both", expand=True, padx=0, pady=0)

        self._ph_id = self._canvas.create_text(
            400, 300,
            text="Start a task to see the agent's view",
            fill=C["muted"], font=("Segoe UI", 11)
        )
        self._img_id = None
        self._tk_img = None

        self._canvas.bind("<Configure>", self._redraw)

    def _redraw(self, e=None):
        if self._ph_id:
            w = self._canvas.winfo_width()
            h = self._canvas.winfo_height()
            self._canvas.coords(self._ph_id, w // 2, h // 2)

    def update_image(self, b64: str):
        try:
            pil = Image.open(BytesIO(base64.b64decode(b64)))
            cw = max(self._canvas.winfo_width(), 100)
            ch = max(self._canvas.winfo_height(), 100)
            pil.thumbnail((cw, ch), Image.LANCZOS)

            self._tk_img = ImageTk.PhotoImage(pil)

            if self._ph_id:
                self._canvas.delete(self._ph_id)
                self._ph_id = None
            if self._img_id:
                self._canvas.delete(self._img_id)

            x, y = cw // 2, ch // 2
            self._img_id = self._canvas.create_image(x, y, anchor="center",
                                                       image=self._tk_img)
        except Exception:
            pass


# ── Pill button ───────────────────────────────────────────────────────────────

def pill_button(parent, text, color, command, width=110):
    f = tk.Frame(parent, bg=color, cursor="hand2")
    lbl = tk.Label(f, text=text, bg=color, fg=C["white"],
                   font=("Segoe UI", 9, "bold"), padx=16, pady=7)
    lbl.pack()
    f.bind("<Button-1>", lambda _: command())
    lbl.bind("<Button-1>", lambda _: command())
    def on_enter(_): f.configure(bg=_darken(color))
    def on_leave(_): f.configure(bg=color)
    for w in (f, lbl):
        w.bind("<Enter>", on_enter)
        w.bind("<Leave>", on_leave)
    return f

def _darken(hex_color: str) -> str:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r, g, b = max(0, r-30), max(0, g-30), max(0, b-30)
    return f"#{r:02x}{g:02x}{b:02x}"


# ── Main Application ──────────────────────────────────────────────────────────

class GUIOCApp(tk.Tk):

    def __init__(self, api_key: str, max_iter: int = 100):
        super().__init__()
        self.api_key  = api_key
        self.max_iter = max_iter
        self._agent   = None
        self._thread: Optional[threading.Thread] = None

        self.title("SVIVIOCLAW — Computer Use Agent")
        self.geometry("1320x800")
        self.minsize(1000, 600)
        self.configure(bg=C["bg"])

        self._build_ui()
        self._poll_events()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top header bar ─────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["sidebar"], height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Logo area
        logo_f = tk.Frame(hdr, bg=C["sidebar"])
        logo_f.pack(side="left", padx=18, pady=0)
        tk.Label(logo_f, text="✦ SVIVIOCLAW", font=("Segoe UI", 15, "bold"),
                 bg=C["sidebar"], fg=C["accent"]).pack(side="left")
        tk.Label(logo_f, text=" Autonomous Computer Use Agent",
                 font=("Segoe UI", 9), bg=C["sidebar"], fg=C["muted"]).pack(side="left")

        # Right: status
        right_f = tk.Frame(hdr, bg=C["sidebar"])
        right_f.pack(side="right", padx=18)
        self._iter_lbl = tk.Label(right_f, text="", font=("Segoe UI", 8),
                                   bg=C["sidebar"], fg=C["muted"])
        self._iter_lbl.pack(side="right", padx=(8, 0))

        self._status_c = tk.Canvas(right_f, width=10, height=10, bg=C["sidebar"],
                                    highlightthickness=0)
        self._status_c.pack(side="right", pady=0)
        self._dot = self._status_c.create_oval(1, 1, 9, 9, fill=C["muted"], outline="")

        tk.Label(right_f, text="Claude Opus 4.6  ", font=("Segoe UI", 8),
                 bg=C["sidebar"], fg=C["muted"]).pack(side="right")

        # ── Three-column layout ────────────────────────────────────────────
        body = tk.PanedWindow(self, orient="horizontal", bg=C["bg"],
                              sashwidth=5, sashrelief="flat", sashpad=0)
        body.pack(fill="both", expand=True)

        # LEFT sidebar
        self._build_sidebar(body)

        # CENTER: chat feed
        center = tk.Frame(body, bg=C["bg"])
        body.add(center, minsize=420, stretch="always")
        self._build_chat(center)

        # RIGHT: live screen
        right = tk.Frame(body, bg=C["bg"])
        body.add(right, minsize=400, stretch="always")
        self._screen = ScreenPanel(right, bg=C["bg"])
        self._screen.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=C["sidebar"], width=230)
        sb.pack_propagate(False)
        parent.add(sb, minsize=200, stretch="never")

        tk.Label(sb, text="TASK", font=("Segoe UI", 8, "bold"),
                 bg=C["sidebar"], fg=C["muted"]).pack(anchor="w", padx=16, pady=(16, 6))

        # Task input
        input_frame = tk.Frame(sb, bg=C["input_bg"],
                               highlightbackground=C["border"], highlightthickness=1)
        input_frame.pack(fill="x", padx=12)

        self._task_text = tk.Text(input_frame, height=5, wrap="word",
                                   bg=C["input_bg"], fg=C["text"],
                                   insertbackground=C["accent"],
                                   relief="flat", bd=0,
                                   font=("Segoe UI", 9),
                                   padx=10, pady=10)
        self._task_text.pack(fill="x")
        self._task_text.insert("1.0", "Open Notepad and write Hello World")
        self._task_text.bind("<Return>", lambda e: (self.start_task(), "break")[1]
                             if not (e.state & 0x1) else None)

        # Buttons
        btn_row = tk.Frame(sb, bg=C["sidebar"])
        btn_row.pack(fill="x", padx=12, pady=8)

        self._run_btn = pill_button(btn_row, "▶  Run", C["accent"], self.start_task)
        self._run_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._stop_btn = pill_button(btn_row, "■", C["err"], self.stop_task)
        self._stop_btn.pack(side="left")

        # Separator
        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=12, pady=4)

        # Failsafe note
        tk.Label(sb, text="⚠  Move mouse to top-left to abort",
                 font=("Segoe UI", 7), bg=C["sidebar"], fg=C["warn"],
                 wraplength=190, justify="left").pack(anchor="w", padx=16, pady=4)

        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=12, pady=4)

        # ── AI Provider ────────────────────────────────────────────────
        tk.Label(sb, text="AI PROVIDER", font=("Segoe UI", 8, "bold"),
                 bg=C["sidebar"], fg=C["muted"]).pack(anchor="w", padx=16, pady=(8, 4))

        self._backend_var = tk.StringVar(value="anthropic")
        for val, lbl in [("anthropic", "Claude (Anthropic)"),
                          ("openrouter", "OpenRouter"),
                          ("ollama", "Ollama (Local)")]:
            tk.Radiobutton(sb, text=lbl, variable=self._backend_var, value=val,
                           bg=C["sidebar"], fg=C["text"], selectcolor=C["surface"],
                           activebackground=C["sidebar"], font=("Segoe UI", 8),
                           command=self._on_provider_change).pack(anchor="w", padx=20)

        # Model field
        tk.Label(sb, text="MODEL (optional)", font=("Segoe UI", 8, "bold"),
                 bg=C["sidebar"], fg=C["muted"]).pack(anchor="w", padx=16, pady=(8, 2))
        self._model_var = tk.StringVar(value="")
        tk.Entry(sb, textvariable=self._model_var, bg=C["input_bg"], fg=C["text"],
                 insertbackground=C["accent"], relief="flat",
                 highlightbackground=C["border"], highlightthickness=1,
                 font=("Segoe UI", 8)).pack(fill="x", padx=12)

        # API key field (for OpenRouter)
        self._key_lbl = tk.Label(sb, text="OPENROUTER API KEY", font=("Segoe UI", 8, "bold"),
                 bg=C["sidebar"], fg=C["muted"])
        self._key_entry_var = tk.StringVar(value=os.environ.get("OPENROUTER_API_KEY",""))
        self._key_entry = tk.Entry(sb, textvariable=self._key_entry_var,
                                    bg=C["input_bg"], fg=C["text"],
                                    insertbackground=C["accent"], relief="flat",
                                    highlightbackground=C["border"], highlightthickness=1,
                                    font=("Segoe UI", 8), show="*")

        # Ollama URL
        self._ollama_lbl = tk.Label(sb, text="OLLAMA URL", font=("Segoe UI", 8, "bold"),
                 bg=C["sidebar"], fg=C["muted"])
        self._ollama_var = tk.StringVar(value="http://localhost:11434")
        self._ollama_entry = tk.Entry(sb, textvariable=self._ollama_var,
                                       bg=C["input_bg"], fg=C["text"],
                                       insertbackground=C["accent"], relief="flat",
                                       highlightbackground=C["border"], highlightthickness=1,
                                       font=("Segoe UI", 8))

        # Max iterations
        tk.Label(sb, text="MAX ITERATIONS", font=("Segoe UI", 8, "bold"),
                 bg=C["sidebar"], fg=C["muted"]).pack(anchor="w", padx=16, pady=(12, 4))

        self._iter_var = tk.StringVar(value=str(self.max_iter))
        spin = tk.Spinbox(sb, from_=5, to=500, increment=5, textvariable=self._iter_var,
                          bg=C["input_bg"], fg=C["text"], buttonbackground=C["surface"],
                          relief="flat", font=("Segoe UI", 9), bd=0,
                          highlightbackground=C["border"], highlightthickness=1)
        spin.pack(fill="x", padx=12)

        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=12, pady=8)

        # ── Task History ────────────────────────────────────────────────
        hdr_row = tk.Frame(sb, bg=C["sidebar"])
        hdr_row.pack(fill="x", padx=16)
        tk.Label(hdr_row, text="HISTORY", font=("Segoe UI", 8, "bold"),
                 bg=C["sidebar"], fg=C["muted"]).pack(side="left")
        refresh_lbl = tk.Label(hdr_row, text="↻", font=("Segoe UI", 10),
                                bg=C["sidebar"], fg=C["muted"], cursor="hand2")
        refresh_lbl.pack(side="right")
        refresh_lbl.bind("<Button-1>", lambda _: self._refresh_history())

        self._history_frame = tk.Frame(sb, bg=C["sidebar"])
        self._history_frame.pack(fill="x", padx=8, pady=(4, 4))
        self._refresh_history()

    def _build_chat(self, parent):
        tk.Label(parent, text="  AGENT CONVERSATION", font=("Segoe UI", 8, "bold"),
                 bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(10, 4))

        self._chat = ChatFeed(parent, bg=C["bg"])
        self._chat.pack(fill="both", expand=True, padx=0)

        # Clear button
        clr = tk.Label(parent, text="Clear log", font=("Segoe UI", 8),
                        bg=C["bg"], fg=C["muted"], cursor="hand2")
        clr.pack(anchor="e", padx=16, pady=4)
        clr.bind("<Button-1>", lambda _: self._chat.clear())

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_history(self, _=None):
        from memory import get_memory
        mem = get_memory()
        tasks = mem.recent_tasks(12)

        for w in self._history_frame.winfo_children():
            w.destroy()

        if not tasks:
            tk.Label(self._history_frame, text="  No history yet",
                     bg=C["sidebar"], fg=C["muted"], font=("Segoe UI", 8)).pack(anchor="w")
            return

        status_icons = {"done": "✓", "failed": "✗", "interrupted": "⚡", "running": "●"}

        for t in tasks:
            icon  = status_icons.get(t["status"], "?")
            color = {
                "done": C["ok"], "failed": C["err"],
                "interrupted": C["warn"], "running": C["accent2"]
            }.get(t["status"], C["muted"])

            row = tk.Frame(self._history_frame, bg=C["sidebar"], cursor="hand2")
            row.pack(fill="x", pady=1)

            tk.Label(row, text=icon, bg=C["sidebar"], fg=color,
                     font=("Segoe UI", 8, "bold"), width=2).pack(side="left")

            snippet = t["task"][:34] + ("…" if len(t["task"]) > 34 else "")
            lbl = tk.Label(row, text=snippet, bg=C["sidebar"], fg=C["muted"],
                           font=("Segoe UI", 8), anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True)

            # Click to reuse task
            lbl.bind("<Button-1>", lambda e, task=t["task"]: self._set_task(task))
            lbl.bind("<Enter>", lambda e, b=lbl: b.configure(fg=C["text"]))
            lbl.bind("<Leave>", lambda e, b=lbl: b.configure(fg=C["muted"]))

            # Resume button for interrupted tasks
            if t["status"] == "interrupted":
                res = tk.Label(row, text="▶", bg=C["sidebar"], fg=C["warn"],
                               font=("Segoe UI", 8), cursor="hand2")
                res.pack(side="right", padx=4)
                res.bind("<Button-1>", lambda e, tid=t["id"], task=t["task"]:
                          self._resume_task(tid, task))

    def _resume_task(self, task_id: int, task: str):
        """Resume an interrupted task from saved messages."""
        if self._agent:
            self._agent.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        try:
            max_iter = int(self._iter_var.get())
        except ValueError:
            max_iter = self.max_iter

        from agent import SVIVIOCLAWAgent
        backend = self._backend_var.get()
        self._agent = SVIVIOCLAWAgent(
            api_key=self.api_key,
            max_iter=max_iter,
            on_event=on_event,
            backend=backend,
            model=self._model_var.get().strip(),
            openrouter_key=self._key_entry_var.get().strip(),
            ollama_url=self._ollama_var.get().strip(),
            resume_task_id=task_id,
        )

        self._chat.clear()
        self._set_running(True)
        self._chat.add_bubble(f"Resuming task #{task_id}: {task}", role="user")

        def run():
            self._agent.run(task)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def _on_provider_change(self):
        backend = self._backend_var.get()
        self._key_lbl.pack_forget()
        self._key_entry.pack_forget()
        self._ollama_lbl.pack_forget()
        self._ollama_entry.pack_forget()
        if backend == "openrouter":
            self._key_lbl.pack(anchor="w", padx=16, pady=(6, 2))
            self._key_entry.pack(fill="x", padx=12)
        elif backend == "ollama":
            self._ollama_lbl.pack(anchor="w", padx=16, pady=(6, 2))
            self._ollama_entry.pack(fill="x", padx=12)

    def _set_task(self, text: str):
        self._task_text.delete("1.0", "end")
        self._task_text.insert("1.0", text)

    def _set_running(self, running: bool):
        col = C["ok"] if running else C["muted"]
        self._status_c.itemconfig(self._dot, fill=col)
        if running:
            self._iter_lbl.configure(text="● Running")
        else:
            self._iter_lbl.configure(text="")

    # ── Agent control ─────────────────────────────────────────────────────────

    def start_task(self):
        task = self._task_text.get("1.0", "end").strip()
        if not task:
            return

        # Stop previous
        if self._agent:
            self._agent.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        try:
            max_iter = int(self._iter_var.get())
        except ValueError:
            max_iter = self.max_iter

        from agent import SVIVIOCLAWAgent
        backend = self._backend_var.get()
        self._agent = SVIVIOCLAWAgent(
            api_key=self.api_key,
            max_iter=max_iter,
            on_event=on_event,
            backend=backend,
            model=self._model_var.get().strip(),
            openrouter_key=self._key_entry_var.get().strip(),
            ollama_url=self._ollama_var.get().strip(),
        )

        self._chat.clear()
        self._set_running(True)
        self._chat.add_bubble(f"Task: {task}", role="user")

        def run():
            self._agent.run(task)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop_task(self):
        if self._agent:
            self._agent.stop()
        self._chat.add_bubble("Agent stopped by user.", role="system")

    # ── Event polling ─────────────────────────────────────────────────────────

    def _poll_events(self):
        try:
            while True:
                event, data = event_queue.get_nowait()
                self._handle_event(event, data)
        except queue.Empty:
            pass
        self.after(80, self._poll_events)

    def _handle_event(self, event: str, data: dict):
        if event == "task_start":
            pass

        elif event == "iteration":
            self._iter_lbl.configure(text=f"● Iter {data['n']}/{data['max']}")

        elif event == "screenshot":
            self._screen.update_image(data["data"])

        elif event == "message":
            self._chat.add_bubble(data["text"], role="agent")

        elif event == "thinking":
            excerpt = data["text"][:200].replace("\n", " ")
            self._chat.add_bubble(excerpt + "…", role="thinking")

        elif event == "action":
            a = data["action"]
            desc = a.get("type", "?").upper()
            if "coordinate" in a:
                desc += f"  ({a['coordinate'][0]}, {a['coordinate'][1]})"
            if "text" in a:
                snip = a["text"][:60]
                desc += f'  "{snip}"'
            if "key" in a:
                desc += f"  [{a['key']}]"
            self._chat.add_bubble(desc, role="action")

        elif event == "action_result":
            self._chat.add_bubble(data["desc"], role="result")

        elif event == "warning":
            self._chat.add_bubble(f"⚠ {data['msg']}", role="system")

        elif event == "memory_event":
            self._chat.add_bubble(f"🧠 {data['msg']}", role="system")

        elif event == "done":
            self._set_running(False)
            self._chat.add_bubble(data["text"], role="agent")
            self._refresh_history()   # update history panel


# ── Entry point ───────────────────────────────────────────────────────────────

def launch_gui(api_key: str, max_iter: int = 100):
    app = GUIOCApp(api_key=api_key, max_iter=max_iter)
    app.mainloop()


if __name__ == "__main__":
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("Set ANTHROPIC_API_KEY first.")
        sys.exit(1)
    launch_gui(key)
