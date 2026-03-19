from __future__ import annotations

import datetime
import os
import secrets
import signal
import subprocess
import threading
from functools import wraps
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for

from config_loader import get_config_value, load_config


BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
SSO_DIR = BASE_DIR / "sso"
RUN_SCRIPT = BASE_DIR / "DrissionPage_example.py"

LOGS_DIR.mkdir(exist_ok=True)
SSO_DIR.mkdir(exist_ok=True)


def _load_webui_config() -> Dict[str, object]:
    conf = load_config()
    return {
        "host": str(get_config_value(conf, "webui.host", "127.0.0.1")).strip() or "127.0.0.1",
        "port": int(get_config_value(conf, "webui.port", 8780) or 8780),
        "username": str(get_config_value(conf, "webui.username", "admin")).strip() or "admin",
        "password": str(get_config_value(conf, "webui.password", "change_me")).strip() or "change_me",
        "secret_key": str(get_config_value(conf, "webui.secret_key", "")).strip() or secrets.token_hex(32),
    }


WEBUI_CONFIG = _load_webui_config()

app = Flask(__name__)
app.secret_key = str(WEBUI_CONFIG["secret_key"])


_runner_lock = threading.Lock()
_runner_process: Optional[subprocess.Popen[str]] = None
_runner_output_lines: list[str] = []
_runner_state: Dict[str, object] = {
    "status": "idle",
    "count": 0,
    "started_at": None,
    "finished_at": None,
    "command": "",
    "return_code": None,
    "output_path": "",
    "error": "",
}


PAGE_TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Grok Register WebUI</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --surface: rgba(255,255,255,0.82);
      --surface-strong: #ffffff;
      --ink: #1f1a14;
      --muted: #6a6257;
      --line: rgba(31,26,20,0.12);
      --accent: #17633f;
      --accent-2: #b35c2e;
      --danger: #b13b2e;
      --shadow: 0 18px 40px rgba(31,26,20,0.08);
      --radius: 18px;
      --mono: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
      --ui: "IBM Plex Sans", "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: var(--ui);
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(23,99,63,0.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(179,92,46,0.12), transparent 24%),
        var(--bg);
    }
    .shell {
      max-width: 1240px;
      margin: 0 auto;
      padding: 28px 18px 40px;
    }
    .hero {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 20px;
    }
    .hero-card, .panel {
      background: var(--surface);
      backdrop-filter: blur(18px);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }
    .hero-card {
      padding: 22px 24px;
      flex: 1;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 30px;
    }
    .muted {
      color: var(--muted);
    }
    .logout {
      border: 0;
      background: var(--accent-2);
      color: white;
      border-radius: 999px;
      padding: 12px 18px;
      cursor: pointer;
      font-weight: 600;
    }
    .grid {
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      gap: 18px;
    }
    .panel {
      padding: 18px;
    }
    .panel h2 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .field {
      display: grid;
      gap: 8px;
      margin-bottom: 14px;
    }
    label {
      font-size: 13px;
      color: var(--muted);
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      background: var(--surface-strong);
      border-radius: 12px;
      padding: 12px 14px;
      font: inherit;
      color: var(--ink);
    }
    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 6px;
    }
    button {
      border: 0;
      border-radius: 12px;
      padding: 12px 16px;
      cursor: pointer;
      font-weight: 600;
      font: inherit;
    }
    .primary {
      background: var(--accent);
      color: white;
    }
    .danger {
      background: var(--danger);
      color: white;
    }
    .ghost {
      background: transparent;
      border: 1px solid var(--line);
      color: var(--ink);
    }
    .pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 4px;
      margin-bottom: 16px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 13px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.68);
    }
    .pill.running {
      color: var(--accent);
    }
    .pill.failed {
      color: var(--danger);
    }
    .pill.completed {
      color: #2d5ea8;
    }
    .stack {
      display: grid;
      gap: 18px;
    }
    .console {
      min-height: 360px;
      max-height: 520px;
      overflow: auto;
      background: #0f1512;
      color: #dcffe8;
      border-radius: 16px;
      padding: 16px;
      font-family: var(--mono);
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .sso-box {
      min-height: 180px;
      max-height: 300px;
      overflow: auto;
      background: #16120f;
      color: #ffe8d8;
      border-radius: 16px;
      padding: 16px;
      font-family: var(--mono);
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .meta {
      display: grid;
      gap: 8px;
      margin-bottom: 14px;
      color: var(--muted);
      font-size: 13px;
    }
    .login-wrap {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }
    .login-card {
      width: min(420px, 100%);
      background: var(--surface);
      backdrop-filter: blur(18px);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 26px;
    }
    .login-card h1 {
      margin: 0 0 10px;
    }
    .error {
      margin-bottom: 12px;
      color: var(--danger);
      font-size: 14px;
    }
    @media (max-width: 980px) {
      .grid {
        grid-template-columns: 1fr;
      }
      .hero {
        flex-direction: column;
        align-items: stretch;
      }
    }
  </style>
</head>
<body>
  {% if login %}
  <div class="login-wrap">
    <form class="login-card" method="post" action="{{ url_for('login') }}">
      <h1>WebUI 登录</h1>
      <p class="muted">登录后可启动注册任务、查看日志和复制 SSO。</p>
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
      <div class="field">
        <label for="username">用户名</label>
        <input id="username" name="username" autocomplete="username" required>
      </div>
      <div class="field">
        <label for="password">密码</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required>
      </div>
      <div class="actions">
        <button class="primary" type="submit">登录</button>
      </div>
    </form>
  </div>
  {% else %}
  <div class="shell">
    <div class="hero">
      <div class="hero-card">
        <h1>Grok Register Panel</h1>
        <div class="muted">启动批量注册、查看实时运行日志、浏览并复制 SSO 文件。</div>
      </div>
      <form method="post" action="{{ url_for('logout') }}">
        <button class="logout" type="submit">退出登录</button>
      </form>
    </div>

    <div class="grid">
      <div class="panel">
        <h2>启动任务</h2>
        <div class="field">
          <label for="run-count">注册数量</label>
          <input id="run-count" type="number" min="1" step="1" value="1">
        </div>
        <div class="actions">
          <button class="primary" id="start-btn" type="button">开始注册</button>
          <button class="danger" id="stop-btn" type="button">停止任务</button>
        </div>
        <div class="pill-row">
          <span class="pill" id="status-pill">状态: idle</span>
          <span class="pill" id="count-pill">数量: 0</span>
        </div>
        <div class="meta" id="task-meta"></div>

        <h2>SSO 文件</h2>
        <div class="field">
          <label for="sso-select">选择文件</label>
          <select id="sso-select"></select>
        </div>
        <div class="actions">
          <button class="ghost" id="refresh-sso-btn" type="button">刷新文件</button>
          <button class="primary" id="copy-sso-btn" type="button">一键复制 SSO</button>
        </div>
      </div>

      <div class="stack">
        <div class="panel">
          <h2>运行日志</h2>
          <div class="console" id="log-console">等待任务启动...</div>
        </div>
        <div class="panel">
          <h2>SSO 内容</h2>
          <div class="sso-box" id="sso-box">暂无内容</div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const statusPill = document.getElementById('status-pill');
    const countPill = document.getElementById('count-pill');
    const taskMeta = document.getElementById('task-meta');
    const logConsole = document.getElementById('log-console');
    const ssoSelect = document.getElementById('sso-select');
    const ssoBox = document.getElementById('sso-box');
    const runCountInput = document.getElementById('run-count');

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || '请求失败');
      }
      return data;
    }

    function renderTaskState(state) {
      const status = state.status || 'idle';
      statusPill.textContent = '状态: ' + status;
      statusPill.className = 'pill ' + status;
      countPill.textContent = '数量: ' + (state.count || 0);

      const lines = [];
      if (state.started_at) lines.push('开始时间: ' + state.started_at);
      if (state.finished_at) lines.push('结束时间: ' + state.finished_at);
      if (state.output_path) lines.push('SSO 输出: ' + state.output_path);
      if (state.return_code !== null && state.return_code !== undefined) lines.push('退出码: ' + state.return_code);
      if (state.error) lines.push('错误: ' + state.error);
      taskMeta.innerHTML = lines.map((line) => '<div>' + line + '</div>').join('');
    }

    async function refreshState() {
      try {
        const data = await fetchJson('/api/state');
        renderTaskState(data.state);
      } catch (error) {
        taskMeta.innerHTML = '<div>状态获取失败: ' + error.message + '</div>';
      }
    }

    async function refreshLogs() {
      try {
        const data = await fetchJson('/api/logs');
        logConsole.textContent = data.content || '暂无日志';
        logConsole.scrollTop = logConsole.scrollHeight;
      } catch (error) {
        logConsole.textContent = '日志获取失败: ' + error.message;
      }
    }

    async function refreshSsoFiles() {
      try {
        const data = await fetchJson('/api/sso-files');
        const current = ssoSelect.value;
        ssoSelect.innerHTML = '';
        for (const item of data.files) {
          const option = document.createElement('option');
          option.value = item.name;
          option.textContent = item.name + ' (' + item.lines + ' 条)';
          if (item.name === current || (!current && item.latest)) {
            option.selected = true;
          }
          ssoSelect.appendChild(option);
        }
        if (ssoSelect.value) {
          await refreshSsoContent();
        } else {
          ssoBox.textContent = '暂无 SSO 文件';
        }
      } catch (error) {
        ssoBox.textContent = 'SSO 文件列表获取失败: ' + error.message;
      }
    }

    async function refreshSsoContent() {
      const file = ssoSelect.value;
      if (!file) {
        ssoBox.textContent = '暂无 SSO 文件';
        return;
      }
      try {
        const data = await fetchJson('/api/sso-content?name=' + encodeURIComponent(file));
        ssoBox.textContent = data.content || '文件为空';
      } catch (error) {
        ssoBox.textContent = 'SSO 内容获取失败: ' + error.message;
      }
    }

    async function startTask() {
      const count = Number(runCountInput.value || '0');
      if (!Number.isInteger(count) || count <= 0) {
        alert('注册数量必须是大于 0 的整数');
        return;
      }
      try {
        const data = await fetchJson('/api/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ count }),
        });
        renderTaskState(data.state);
        await refreshLogs();
        await refreshSsoFiles();
      } catch (error) {
        alert(error.message);
      }
    }

    async function stopTask() {
      try {
        const data = await fetchJson('/api/stop', { method: 'POST' });
        renderTaskState(data.state);
      } catch (error) {
        alert(error.message);
      }
    }

    async function copySso() {
      const text = ssoBox.textContent || '';
      if (!text.trim()) {
        alert('当前没有可复制的 SSO 内容');
        return;
      }
      await navigator.clipboard.writeText(text);
      alert('已复制当前 SSO 内容');
    }

    document.getElementById('start-btn').addEventListener('click', startTask);
    document.getElementById('stop-btn').addEventListener('click', stopTask);
    document.getElementById('refresh-sso-btn').addEventListener('click', refreshSsoFiles);
    document.getElementById('copy-sso-btn').addEventListener('click', copySso);
    ssoSelect.addEventListener('change', refreshSsoContent);

    refreshState();
    refreshLogs();
    refreshSsoFiles();
    setInterval(refreshState, 3000);
    setInterval(refreshLogs, 3000);
    setInterval(refreshSsoFiles, 5000);
  </script>
  {% endif %}
</body>
</html>
"""


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "未登录"}), 401
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)

    return wrapped


def _iso_now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _latest_log_file() -> Optional[Path]:
    files = sorted(LOGS_DIR.glob("run_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _list_sso_files() -> list[Dict[str, object]]:
    files = sorted(SSO_DIR.glob("sso_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for index, path in enumerate(files):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            content = ""
        lines = [line for line in content.splitlines() if line.strip()]
        result.append({
            "name": path.name,
            "path": str(path),
            "lines": len(lines),
            "latest": index == 0,
        })
    return result


def _read_sso_content(name: str) -> str:
    target = (SSO_DIR / name).resolve()
    if target.parent != SSO_DIR.resolve() or not target.exists():
        raise FileNotFoundError("SSO 文件不存在")
    return target.read_text(encoding="utf-8")


def _build_run_command(count: int) -> tuple[list[str], Path]:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = SSO_DIR / f"sso_webui_{ts}.txt"
    command = [
        os.environ.get("PYTHON", "python"),
        str(RUN_SCRIPT),
        "--count",
        str(count),
        "--output",
        str(output_path),
    ]
    return command, output_path


def _runner_thread(process: subprocess.Popen[str], count: int, output_path: Path, command: list[str]) -> None:
    return_code = process.wait()
    with _runner_lock:
        _runner_state["finished_at"] = _iso_now()
        _runner_state["return_code"] = return_code
        _runner_state["output_path"] = str(output_path)
        _runner_state["command"] = " ".join(command)
        if return_code == 0:
            _runner_state["status"] = "completed"
            _runner_state["error"] = ""
        else:
            _runner_state["status"] = "failed"
            _runner_state["error"] = f"注册任务退出码为 {return_code}"
        global _runner_process
        _runner_process = None


def _consume_process_output(process: subprocess.Popen[str]) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        with _runner_lock:
            _runner_output_lines.append(line.rstrip("\n"))
            if len(_runner_output_lines) > 2000:
                del _runner_output_lines[:500]


@app.get("/")
def login_page():
    if session.get("authenticated"):
        return render_template_string(PAGE_TEMPLATE, login=False)
    return render_template_string(PAGE_TEMPLATE, login=True, error=None)


@app.post("/login")
def login():
    username = str(request.form.get("username", "")).strip()
    password = str(request.form.get("password", "")).strip()
    if username == WEBUI_CONFIG["username"] and password == WEBUI_CONFIG["password"]:
        session["authenticated"] = True
        return redirect(url_for("login_page"))
    return render_template_string(PAGE_TEMPLATE, login=True, error="用户名或密码错误")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.get("/api/state")
@login_required
def api_state():
    with _runner_lock:
        return jsonify({"state": dict(_runner_state)})


@app.post("/api/start")
@login_required
def api_start():
    payload = request.get_json(silent=True) or {}
    try:
        count = int(payload.get("count", 0) or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "注册数量必须是整数"}), 400
    if count <= 0:
        return jsonify({"error": "注册数量必须大于 0"}), 400

    with _runner_lock:
        global _runner_process
        if _runner_process is not None and _runner_process.poll() is None:
            return jsonify({"error": "当前已有任务在运行中"}), 409

        command, output_path = _build_run_command(count)
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
            bufsize=1,
        )
        _runner_process = process
        _runner_output_lines.clear()
        _runner_state.update({
            "status": "running",
            "count": count,
            "started_at": _iso_now(),
            "finished_at": None,
            "command": " ".join(command),
            "return_code": None,
            "output_path": str(output_path),
            "error": "",
        })
        thread = threading.Thread(
            target=_runner_thread,
            args=(process, count, output_path, command),
            daemon=True,
        )
        thread.start()
        output_thread = threading.Thread(target=_consume_process_output, args=(process,), daemon=True)
        output_thread.start()
        return jsonify({"state": dict(_runner_state)})


@app.post("/api/stop")
@login_required
def api_stop():
    with _runner_lock:
        global _runner_process
        if _runner_process is None or _runner_process.poll() is not None:
            return jsonify({"error": "当前没有运行中的任务"}), 409

        try:
            if os.name == "nt":
                _runner_process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[arg-type]
            else:
                _runner_process.terminate()
        except Exception:
            _runner_process.kill()

        _runner_state["status"] = "stopping"
        _runner_state["error"] = "停止请求已发送"
        return jsonify({"state": dict(_runner_state)})


@app.get("/api/logs")
@login_required
def api_logs():
    with _runner_lock:
        content = "\n".join(_runner_output_lines).strip()
    if content:
        return jsonify({"name": "live", "content": content[-60000:]})

    latest = _latest_log_file()
    if not latest:
        return jsonify({"content": ""})
    try:
        content = latest.read_text(encoding="utf-8")
    except Exception as exc:
        return jsonify({"error": f"读取日志失败: {exc}"}), 500
    return jsonify({"name": latest.name, "content": content[-60000:]})


@app.get("/api/sso-files")
@login_required
def api_sso_files():
    return jsonify({"files": _list_sso_files()})


@app.get("/api/sso-content")
@login_required
def api_sso_content():
    name = str(request.args.get("name", "")).strip()
    if not name:
        return jsonify({"error": "缺少文件名"}), 400
    try:
        content = _read_sso_content(name)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"name": name, "content": content})


def main() -> None:
    app.run(
        host=str(WEBUI_CONFIG["host"]),
        port=int(WEBUI_CONFIG["port"]),
        debug=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
