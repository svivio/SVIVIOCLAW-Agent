#!/usr/bin/env python3
"""
GUIOC - GUI Operator Computer Use Agent
CLI entry point. Competes with OpenHands, Manus, Perplexity Computer.

Usage:
    python guioc.py "Open Notepad and type Hello World"
    python guioc.py --interactive
    python guioc.py --web          (launches browser dashboard)
"""

import os
import sys
import argparse
import logging
import threading
from datetime import datetime

# ── Logging setup ─────────────────────────────────────────────────────────────
log_file = f"guioc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("guioc")

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║          SVIVIOCLAW — Autonomous Computer Use AI Agent           ║
║    Powered by Claude Opus 4.6  •  Windows 11  •  By Vivaan.io   ║
║    Competing: OpenClaw | Manus | Perplexity Computer             ║
╚══════════════════════════════════════════════════════════════════╝
  ⚠  FAILSAFE: move mouse to top-left corner of screen to abort
"""


def check_api_key(key: str | None) -> str:
    k = key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not k:
        print("\n[ERROR] No Anthropic API key found.")
        print("  Set it with:  set ANTHROPIC_API_KEY=sk-ant-...")
        print("  Or pass:      --api-key sk-ant-...")
        sys.exit(1)
    return k


def cli_event(event: str, data: dict):
    """Print events to the terminal in real time."""
    if event == "task_start":
        print(f"\n[TASK] {data['task']}\n")
    elif event == "iteration":
        print(f"\n{'─'*50}")
        print(f"  Iteration {data['n']} / {data['max']}")
        print(f"{'─'*50}")
    elif event == "thinking":
        excerpt = data["text"][:200].replace("\n", " ")
        print(f"  [Thinking…] {excerpt}…")
    elif event == "message":
        print(f"\n[Claude] {data['text']}")
    elif event == "action":
        a = data["action"]
        print(f"  → {a.get('type','?').upper()}", end="")
        if "coordinate" in a:
            print(f" at {a['coordinate']}", end="")
        if "text" in a:
            print(f" | text='{a['text'][:60]}'", end="")
        if "key" in a:
            print(f" | key={a['key']}", end="")
        print()
    elif event == "action_result":
        print(f"    ✓ {data['desc']}")
    elif event == "warning":
        print(f"\n  ⚠ {data['msg']}")
    elif event == "done":
        print(f"\n{'═'*60}")
        print(f"[DONE] {data['text']}")
        print(f"{'═'*60}\n")


def run_cli(task: str, api_key: str, max_iter: int):
    from agent import GUIOCAgent
    agent = GUIOCAgent(api_key=api_key, max_iter=max_iter, on_event=cli_event)
    result = agent.run(task)
    return result


def run_interactive(api_key: str, max_iter: int):
    from agent import GUIOCAgent
    agent = GUIOCAgent(api_key=api_key, max_iter=max_iter, on_event=cli_event)
    print("Interactive mode — type 'quit' to exit\n")
    while True:
        try:
            task = input("\nTask> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if task.lower() in ("quit", "exit", "q", ""):
            break
        agent.run(task)
        agent._messages.clear()
        agent._iter = 0


def run_web(api_key: str, max_iter: int, port: int = 7788):
    """Launch the web dashboard."""
    from server import create_app
    import uvicorn

    app = create_app(api_key=api_key, max_iter=max_iter)
    url = f"http://localhost:{port}"
    print(f"\n[Web] Dashboard: {url}")

    # Open browser after short delay
    def open_browser():
        import time, webbrowser
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GUIOC – Autonomous Computer Use AI Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python guioc.py "Open Notepad and write a poem"
  python guioc.py "Search YouTube for lofi music and play the first result"
  python guioc.py "Open File Explorer, go to Downloads, delete files older than 7 days"
  python guioc.py --interactive
  python guioc.py --web
        """,
    )
    parser.add_argument("task", nargs="?", help="Task for the agent to complete")
    parser.add_argument("--api-key", help="Anthropic API key")
    parser.add_argument("--max-iter", type=int, default=100, help="Max agent iterations (default: 100)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive multi-task mode")
    parser.add_argument("--web", "-w", action="store_true", help="Launch web dashboard")
    parser.add_argument("--port", type=int, default=7788, help="Web dashboard port (default: 7788)")
    parser.add_argument("--gui", "-g", action="store_true", help="Launch native desktop GUI")

    args = parser.parse_args()
    print(BANNER)

    api_key = check_api_key(args.api_key)

    if args.gui:
        from gui import launch_gui
        launch_gui(api_key, args.max_iter)
    elif args.web:
        run_web(api_key, args.max_iter, args.port)
    elif args.interactive:
        run_interactive(api_key, args.max_iter)
    elif args.task:
        run_cli(args.task, api_key, args.max_iter)
    else:
        # Default: ask for a task
        print("No task given. What should the agent do?\n")
        task = input("Task> ").strip()
        if task:
            run_cli(task, api_key, args.max_iter)
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
