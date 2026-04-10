"""
GUIOC Web Server — FastAPI + WebSocket real-time dashboard
"""

import asyncio
import json
import threading
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

# ── HTML Dashboard ────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SVIVIOCLAW — Computer Use Agent</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --accent: #7c3aed; --accent2: #06b6d4; --text: #e6edf3;
    --muted: #8b949e; --ok: #3fb950; --warn: #f0883e; --err: #f85149;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; height: 100vh; display: flex; flex-direction: column; }

  header {
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 12px 20px; display: flex; align-items: center; gap: 16px;
  }
  .logo { font-size: 1.4rem; font-weight: 700; color: var(--accent); letter-spacing: -0.5px; }
  .badge { font-size: 0.72rem; background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 20px; }
  .status-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--muted); margin-left: auto; transition: background 0.3s; }
  .status-dot.running { background: var(--ok); box-shadow: 0 0 8px var(--ok); animation: pulse 1.2s infinite; }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.4 } }

  main { flex: 1; display: grid; grid-template-columns: 1fr 380px; gap: 0; overflow: hidden; }

  .screen-panel { padding: 16px; display: flex; flex-direction: column; gap: 12px; overflow: hidden; }
  .screen-panel h2 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); }
  #screen-img {
    width: 100%; border-radius: 8px; border: 1px solid var(--border);
    background: #000; object-fit: contain; max-height: calc(100vh - 160px);
  }
  .screen-placeholder {
    width: 100%; aspect-ratio: 16/9; border-radius: 8px; border: 2px dashed var(--border);
    display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 0.9rem;
  }

  .side-panel { border-left: 1px solid var(--border); display: flex; flex-direction: column; }

  .task-box { padding: 16px; border-bottom: 1px solid var(--border); }
  .task-box h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 10px; }
  textarea#task-input {
    width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 10px; border-radius: 6px; resize: none; height: 80px; font-size: 0.9rem;
    outline: none; transition: border-color 0.2s;
  }
  textarea#task-input:focus { border-color: var(--accent); }
  .btn-row { display: flex; gap: 8px; margin-top: 10px; }
  button {
    padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer;
    font-size: 0.875rem; font-weight: 600; transition: opacity 0.15s;
  }
  button:hover { opacity: 0.85; }
  #btn-run { background: var(--accent); color: #fff; flex: 1; }
  #btn-stop { background: var(--err); color: #fff; }
  #btn-stop:disabled { opacity: 0.4; cursor: not-allowed; }

  .iter-bar { padding: 8px 16px; border-bottom: 1px solid var(--border); font-size: 0.8rem; color: var(--muted); display: flex; gap: 12px; align-items: center; }
  .iter-bar span { color: var(--text); font-weight: 600; }

  .log-panel { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 6px; }
  .log-panel h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 6px; position: sticky; top: 0; background: var(--surface); padding: 4px 0; }

  .log-entry {
    padding: 7px 10px; border-radius: 6px; font-size: 0.82rem; line-height: 1.4;
    border-left: 3px solid transparent;
  }
  .log-entry.message  { background: #1c2128; border-color: var(--accent2); }
  .log-entry.action   { background: #161b22; border-color: var(--accent); font-family: monospace; }
  .log-entry.result   { background: #161b22; border-color: var(--ok); color: var(--ok); }
  .log-entry.thinking { background: #0d1117; border-color: var(--muted); color: var(--muted); font-style: italic; }
  .log-entry.done     { background: #1c2b1c; border-color: var(--ok); color: var(--ok); font-weight: 600; }
  .log-entry.warning  { background: #1f1a12; border-color: var(--warn); color: var(--warn); }
  .log-entry.system   { color: var(--muted); font-size: 0.75rem; }

  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>

<header>
  <span class="logo">SVIVIOCLAW</span>
  <span class="badge">Computer Use Agent</span>
  <span style="color:var(--muted);font-size:0.8rem">Powered by Claude Opus 4.6 • by Vivaan.io</span>
  <div class="status-dot" id="status-dot"></div>
</header>

<main>
  <!-- Left: live screen -->
  <div class="screen-panel">
    <h2>Live Screen</h2>
    <div id="screen-wrap">
      <div class="screen-placeholder" id="screen-placeholder">
        ▶ Start a task to see the agent's view
      </div>
      <img id="screen-img" style="display:none" alt="Agent Screen">
    </div>
  </div>

  <!-- Right: controls + log -->
  <div class="side-panel">
    <div class="task-box">
      <h2>Task</h2>
      <textarea id="task-input" placeholder="What should the agent do?&#10;E.g.: Open Notepad and write a haiku about Windows"></textarea>
      <div class="btn-row">
        <button id="btn-run" onclick="startTask()">▶ Run</button>
        <button id="btn-stop" onclick="stopTask()" disabled>■ Stop</button>
      </div>
    </div>

    <div class="iter-bar">
      Iteration <span id="iter-n">—</span> / <span id="iter-max">—</span>
    </div>

    <div class="log-panel">
      <h2>Agent Log</h2>
      <div id="log-entries"></div>
    </div>
  </div>
</main>

<script>
let ws = null;
let isRunning = false;

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => addLog('Connected to GUIOC server.', 'system');
  ws.onclose = () => {
    addLog('Disconnected. Reconnecting in 3s…', 'warning');
    setTimeout(connect, 3000);
  };
  ws.onerror = () => addLog('WebSocket error.', 'warning');

  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    handleEvent(msg.event, msg.data);
  };
}

function handleEvent(event, data) {
  const dot = document.getElementById('status-dot');

  if (event === 'task_start') {
    isRunning = true;
    dot.classList.add('running');
    document.getElementById('btn-run').disabled = true;
    document.getElementById('btn-stop').disabled = false;
    document.getElementById('log-entries').innerHTML = '';
    addLog(`Task: ${data.task}`, 'system');

  } else if (event === 'iteration') {
    document.getElementById('iter-n').textContent = data.n;
    document.getElementById('iter-max').textContent = data.max;

  } else if (event === 'screenshot') {
    const img = document.getElementById('screen-img');
    const placeholder = document.getElementById('screen-placeholder');
    img.src = `data:image/png;base64,${data.data}`;
    img.style.display = 'block';
    placeholder.style.display = 'none';

  } else if (event === 'message') {
    addLog(data.text, 'message');

  } else if (event === 'thinking') {
    const excerpt = data.text.substring(0, 160).replace(/\n/g, ' ');
    addLog(`Thinking… ${excerpt}`, 'thinking');

  } else if (event === 'action') {
    const a = data.action;
    let desc = a.type.toUpperCase();
    if (a.coordinate) desc += ` @ (${a.coordinate.join(', ')})`;
    if (a.text)       desc += ` → "${a.text.substring(0,60)}"`;
    if (a.key)        desc += ` → ${a.key}`;
    addLog(desc, 'action');

  } else if (event === 'action_result') {
    addLog(`✓ ${data.desc}`, 'result');

  } else if (event === 'warning') {
    addLog(`⚠ ${data.msg}`, 'warning');

  } else if (event === 'done') {
    isRunning = false;
    dot.classList.remove('running');
    document.getElementById('btn-run').disabled = false;
    document.getElementById('btn-stop').disabled = true;
    addLog(`✅ ${data.text}`, 'done');
  }
}

function addLog(text, cls) {
  const container = document.getElementById('log-entries');
  const div = document.createElement('div');
  div.className = `log-entry ${cls}`;
  div.textContent = text;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function startTask() {
  const task = document.getElementById('task-input').value.trim();
  if (!task) { alert('Please enter a task.'); return; }
  if (!ws || ws.readyState !== WebSocket.OPEN) { alert('Not connected yet.'); return; }
  ws.send(JSON.stringify({ command: 'run', task }));
}

function stopTask() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ command: 'stop' }));
  }
}

// Enter to submit (Shift+Enter for newline)
document.getElementById('task-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startTask(); }
});

connect();
</script>
</body>
</html>
"""


# ── FastAPI App ───────────────────────────────────────────────────────────────

def create_app(api_key: str, max_iter: int = 100) -> FastAPI:
    app = FastAPI(title="GUIOC Web Dashboard")
    active_clients: list[WebSocket] = []
    agent_thread: Optional[threading.Thread] = None
    agent_instance = None

    async def broadcast(event: str, **data):
        msg = json.dumps({"event": event, "data": data})
        dead = []
        for ws in active_clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            active_clients.remove(ws)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        nonlocal agent_thread, agent_instance
        await websocket.accept()
        active_clients.append(websocket)

        loop = asyncio.get_event_loop()

        def on_event(event: str, data: dict):
            asyncio.run_coroutine_threadsafe(
                broadcast(event, **data), loop
            )

        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                command = msg.get("command")

                if command == "run":
                    task = msg.get("task", "").strip()
                    if not task:
                        continue

                    # Stop previous run
                    if agent_instance:
                        agent_instance.stop()
                    if agent_thread and agent_thread.is_alive():
                        agent_thread.join(timeout=3)

                    from agent import GUIOCAgent
                    agent_instance = GUIOCAgent(
                        api_key=api_key,
                        max_iter=max_iter,
                        on_event=on_event,
                    )

                    def run_agent():
                        agent_instance.run(task)

                    agent_thread = threading.Thread(target=run_agent, daemon=True)
                    agent_thread.start()

                elif command == "stop":
                    if agent_instance:
                        agent_instance.stop()

        except WebSocketDisconnect:
            active_clients.remove(websocket)
        except Exception as exc:
            if websocket in active_clients:
                active_clients.remove(websocket)

    return app
