#!/usr/bin/env python3
"""
Simple web editor for users.json configuration.
Run this script and open http://localhost:8899 in your browser.
"""

import json
import os
import sqlite3
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "users.json"
DB_FILE = SCRIPT_DIR / "data" / "twitter.db"
PORT = 8899


def get_user_stats() -> dict:
    """Return latest scan stats per username from the operation_log table.

    Returns a dict keyed by username with fields:
      end_time, total_scanned, new_tweets, status
    """
    if not DB_FILE.exists():
        return {}
    try:
        conn = sqlite3.connect(str(DB_FILE))
        conn.row_factory = sqlite3.Row
        cur = conn.execute("""
            SELECT username, end_time, total_scanned, new_tweets, status
            FROM operation_log
            WHERE id IN (SELECT MAX(id) FROM operation_log GROUP BY username)
              AND end_time IS NOT NULL
        """)
        stats = {}
        for row in cur.fetchall():
            stats[row["username"]] = {
                "end_time": row["end_time"],
                "total_scanned": row["total_scanned"],
                "new_tweets": row["new_tweets"],
                "status": row["status"],
            }
        conn.close()
        return stats
    except Exception:
        return {}

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>用户配置编辑器</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f5f5f5; color: #333; min-height: 100vh;
  }
  .header {
    background: #1a1a2e; color: #fff;
    padding: 20px 24px; display: flex; justify-content: space-between; align-items: center;
  }
  .header h1 { font-size: 1.4rem; font-weight: 600; }
  .header .stats { font-size: 0.85rem; opacity: 0.8; }
  .container { max-width: 800px; margin: 24px auto; padding: 0 16px; }
  .toolbar {
    display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    margin-bottom: 16px;
  }
  .toolbar input[type="text"] {
    flex: 1; min-width: 200px;
    padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px;
    font-size: 0.95rem;
  }
  .toolbar button {
    padding: 8px 18px; border: none; border-radius: 6px;
    font-size: 0.9rem; font-weight: 500; cursor: pointer;
    transition: background 0.15s;
  }
  .btn-enable-all  { background: #4caf50; color: #fff; }
  .btn-disable-all { background: #f44336; color: #fff; }
  .btn-save { background: #2196f3; color: #fff; }
  .btn-save:disabled { background: #90caf9; cursor: not-allowed; }
  .card {
    background: #fff; border-radius: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; }
  thead { background: #fafafa; }
  th {
    text-align: left; padding: 12px 16px;
    font-size: 0.8rem; font-weight: 600; color: #888;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  td { padding: 12px 16px; border-top: 1px solid #f0f0f0; }
  tr:hover { background: #fafcff; }
  .user-cell { display: flex; align-items: center; gap: 10px; }
  .avatar {
    width: 36px; height: 36px; border-radius: 50%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff; display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem; font-weight: 600; flex-shrink: 0;
  }
  .user-info .display-name { font-weight: 500; }
  .user-info .username { font-size: 0.8rem; color: #999; }
  .toggle {
    position: relative; display: inline-block; width: 44px; height: 24px;
  }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute; cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background: #ccc; border-radius: 24px;
    transition: background 0.2s;
  }
  .slider::before {
    content: ""; position: absolute;
    height: 18px; width: 18px; left: 3px; bottom: 3px;
    background: #fff; border-radius: 50%;
    transition: transform 0.2s;
  }
  .toggle input:checked + .slider { background: #4caf50; }
  .toggle input:checked + .slider::before { transform: translateX(20px); }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 10px;
    font-size: 0.75rem; font-weight: 600;
  }
  .badge-on  { background: #e8f5e9; color: #2e7d32; }
  .badge-off { background: #f5f5f5; color: #999; }
  .scan-info {
    font-size: 0.75rem; color: #888; margin-top: 2px;
    display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: center;
  }
  .scan-info .status-ok { color: #2e7d32; font-weight: 500; }
  .scan-info .status-fail { color: #e53935; font-weight: 500; }
  .scan-info .sep { color: #ddd; }
  .toast {
    position: fixed; bottom: 24px; right: 24px;
    padding: 12px 24px; border-radius: 8px;
    color: #fff; font-weight: 500; font-size: 0.9rem;
    opacity: 0; transform: translateY(10px);
    transition: all 0.3s; pointer-events: none; z-index: 999;
  }
  .toast.show  { opacity: 1; transform: translateY(0); }
  .toast.ok    { background: #4caf50; }
  .toast.error { background: #f44336; }
  .empty { text-align: center; padding: 48px; color: #aaa; }
  .footer {
    text-align: center; padding: 24px; font-size: 0.8rem; color: #bbb;
  }
</style>
</head>
<body>
<div class="header">
  <h1>⚙ 用户配置编辑器</h1>
  <span class="stats" id="stats"></span>
</div>
<div class="container">
  <div class="toolbar">
    <input type="text" id="search" placeholder="搜索用户名或昵称…">
    <button class="btn-enable-all" onclick="setAll(true)">全部启用</button>
    <button class="btn-disable-all" onclick="setAll(false)">全部禁用</button>
    <button class="btn-save" id="saveBtn" onclick="doSave()">💾 保存</button>
  </div>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>用户</th>
          <th style="text-align:center;width:100px">状态</th>
          <th style="text-align:center;width:80px">启用</th>
          <th style="width:180px">上次扫描</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty" hidden>没有匹配的用户</div>
  </div>
</div>
<div class="footer">配置将保存到 users.json · 修改后请点击保存按钮</div>
<div class="toast" id="toast"></div>

<script>
let users = [];
let scanStats = {};
let dirty = false;
const EMPTY = document.getElementById('empty');
const TBODY = document.getElementById('tbody');
const SAVE_BTN = document.getElementById('saveBtn');
const STATS = document.getElementById('stats');
const SEARCH = document.getElementById('search');
const TOAST_EL = document.getElementById('toast');
let toastTimer;

function toast(msg, ok) {
  clearTimeout(toastTimer);
  TOAST_EL.textContent = msg;
  TOAST_EL.className = 'toast ' + (ok ? 'ok' : 'error') + ' show';
  toastTimer = setTimeout(() => TOAST_EL.classList.remove('show'), 2000);
}

function markDirty() {
  dirty = true;
  SAVE_BTN.disabled = false;
  SAVE_BTN.textContent = '💾 保存 (有未保存更改)';
}

async function load() {
  try {
    const [ur, sr] = await Promise.all([
      fetch('/api/users'),
      fetch('/api/user-stats')
    ]);
    if (!ur.ok) throw new Error(ur.statusText);
    users = await ur.json();
    if (sr.ok) scanStats = await sr.json();
    render();
    dirty = false;
    SAVE_BTN.disabled = true;
    SAVE_BTN.textContent = '💾 保存';
  } catch (e) {
    toast('加载失败: ' + e.message, false);
  }
}

function fmtTime(iso) {
  if (!iso) return '';
  // Extract just the datetime portion (strip fractional seconds)
  const m = iso.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
  return m ? m[1] : iso;
}

function renderScanInfo(username) {
  const s = scanStats[username];
  if (!s || !s.end_time) return '';
  const ok = s.status === 'success';
  const cls = ok ? 'status-ok' : 'status-fail';
  const icon = ok ? '✓' : '✗';
  const label = ok ? '成功' : '失败';
  return `<div class="scan-info">
    <span>${fmtTime(s.end_time)}</span>
    <span class="sep">·</span>
    <span>扫描 ${s.total_scanned}</span>
    <span class="sep">·</span>
    <span>新增 ${s.new_tweets}</span>
    <span class="${cls}">${icon} ${label}</span>
  </div>`;
}

function render() {
  const q = SEARCH.value.toLowerCase().trim();
  const filtered = q ? users.filter(u =>
    u.username.toLowerCase().includes(q) ||
    (u.display_name || '').toLowerCase().includes(q)
  ) : users;

  EMPTY.hidden = filtered.length > 0;
  STATS.textContent = `共 ${users.length} 个用户 · 已启用 ${users.filter(u => u.enabled).length} 个`;

  TBODY.innerHTML = filtered.map(u => `
    <tr>
      <td>
        <div class="user-cell">
          <div class="avatar">${(u.display_name || u.username)[0].toUpperCase()}</div>
          <div class="user-info">
            <div class="display-name">${esc(u.display_name || u.username)}</div>
            <div class="username">@${esc(u.username)}</div>
            ${renderScanInfo(u.username)}
          </div>
        </div>
      </td>
      <td style="text-align:center">
        <span class="badge ${u.enabled ? 'badge-on' : 'badge-off'}">${u.enabled ? '已启用' : '已禁用'}</span>
      </td>
      <td style="text-align:center">
        <label class="toggle">
          <input type="checkbox" ${u.enabled ? 'checked' : ''}
            onchange="toggleUser('${esc(u.username)}', this.checked)">
          <span class="slider"></span>
        </label>
      </td>
      <td style="font-size:0.8rem;color:#888;vertical-align:top">
        ${renderScanInfoCompact(u.username)}
      </td>
    </tr>
  `).join('');
}

function renderScanInfoCompact(username) {
  const s = scanStats[username];
  if (!s || !s.end_time) return '<span style="color:#ccc">—</span>';
  const ok = s.status === 'success';
  const cls = ok ? 'status-ok' : 'status-fail';
  const icon = ok ? '✓' : '✗';
  const label = ok ? '成功' : '失败';
  return `<div style="line-height:1.5">
    <div>${fmtTime(s.end_time)}</div>
    <div>扫描 <b>${s.total_scanned}</b> · 新增 <b>${s.new_tweets}</b></div>
    <div class="${cls}">${icon} ${label}</div>
  </div>`;
}

function esc(s) { return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function toggleUser(username, enabled) {
  const u = users.find(x => x.username === username);
  if (u) { u.enabled = enabled; render(); markDirty(); }
}

function setAll(enabled) {
  users.forEach(u => u.enabled = enabled);
  render(); markDirty();
}

async function doSave() {
  SAVE_BTN.disabled = true;
  SAVE_BTN.textContent = '⏳ 保存中…';
  try {
    const r = await fetch('/api/users', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(users.map(u => ({
        username: u.username,
        display_name: u.display_name,
        enabled: u.enabled
      })))
    });
    if (!r.ok) throw new Error(await r.text() || r.statusText);
    dirty = false;
    SAVE_BTN.textContent = '💾 保存';
    toast('保存成功', true);
  } catch (e) {
    SAVE_BTN.disabled = false;
    SAVE_BTN.textContent = '💾 保存 (有未保存更改)';
    toast('保存失败: ' + e.message, false);
  }
}

SEARCH.addEventListener('input', render);
load();
</script>
</body>
</html>"""


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Suppress access logs
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._send_html(HTML)
        elif path == "/api/users":
            config = load_config()
            self._send_json(config.get("users", []))
        elif path == "/api/user-stats":
            self._send_json(get_user_stats())
        else:
            self._send_json({"error": "not found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if path == "/api/users":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError) as e:
                self._send_json({"error": f"Invalid request body: {e}"}, 400)
                return

            if not isinstance(body, list):
                self._send_json({"error": "Expected a list of users"}, 400)
                return

            config = load_config()
            original_users = config.get("users", [])

            # Update enabled status for matching usernames
            incoming = {u["username"]: u for u in body}
            for orig in original_users:
                if orig["username"] in incoming:
                    orig["enabled"] = incoming[orig["username"]].get("enabled", orig["enabled"])

            config["users"] = original_users
            save_config(config)
            self._send_json({"ok": True, "count": len(original_users)})
        else:
            self._send_json({"error": "not found"}, 404)


def main():
    print(f"\n  📝 用户配置编辑器")
    print(f"  ─────────────────────")
    print(f"  配置文件: {CONFIG_FILE}")
    print(f"  地址:     http://localhost:{PORT}")
    print(f"\n  按 Ctrl+C 停止服务器\n")

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
        server.server_close()
        sys.exit(0)


if __name__ == "__main__":
    main()
