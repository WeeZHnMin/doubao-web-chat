#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_login.py — 首次初始化（无 Playwright，纯标准库 + 正式版浏览器 CDP）

原理：
    用 subprocess 拉起正式版 Chrome/Edge（带 --remote-debugging-port），
    通过 Chrome DevTools Protocol(CDP) 走 WebSocket 读 cookie/localStorage、
    拦截 /web/r/token 请求拿到 strData，再解密成设备指纹，写两个 json。

前提：
    - 本机已装 Chrome 或 Edge
    - 仅 Python 标准库（socket/hashlib/base64/struct/json），无需 pip 安装任何东西

用法：
    python setup_login.py                    # 用 Chrome
    python setup_login.py --browser edge     # 用 Edge
    python setup_login.py --profile <目录>    # 登录态持久化目录（默认 ./browser_profile）
    python setup_login.py --port 9222        # 远程调试端口（默认 9222）

流程：
    1. 拉起正式版浏览器（持久化登录态）
    2. 你在这个浏览器里登录 doubao.com/chat
    3. 登录后回终端按回车
    4. 脚本自动抓取并生成 doubao_identity.json + fingerprint_template.json
"""

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request
import uuid

import mssdk

HERE = os.path.dirname(os.path.abspath(__file__))
IDENTITY_FILE = os.path.join(HERE, "doubao_identity.json")
FINGERPRINT_FILE = os.path.join(HERE, "fingerprint_template.json")
DOUBAO_URL = "https://www.doubao.com/chat"

CONST_DEVICE = {
    "aid": "497858",
    "real_aid": "497858",
    "region": "CN",
    "sys_region": "CN",
    "language": "zh",
    "tz_name": "Asia/Shanghai",
    "os": "windows",
    "device_platform": "web",
    "doubao_device_platform": "web",
    "web_platform": "browser",
    "pkg_type": "release_version",
    "samantha_web": "1",
    "use_olympus_account": "1",
    "version_code": "20800",
    "pc_version": "3.47.2",
    "doubao_pc_version": "3.47.2",
}
BOT_ID = "7338286299411103781"


# ---------------------------------------------------------------------------
# 最小 WebSocket 客户端（RFC6455，仅够 CDP 用）
# ---------------------------------------------------------------------------
class WS:
    def __init__(self, url):
        # ws://host:port/path
        self.url = url
        rest = url.split("://", 1)[1]
        hostport, _, path = rest.partition("/")
        self.host, _, port = hostport.partition(":")
        self.port = int(port or 80)
        self.path = "/" + path
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        self.sock.settimeout(30)
        self._handshake()

    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        # 读响应头直到 \r\n\r\n
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("WebSocket 握手失败")
            data += chunk
        if b"101" not in data.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"WebSocket 握手非 101: {data[:200]}")

    def _recv_exact(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise RuntimeError("WebSocket 连接关闭")
            data += chunk
        return data

    def send_text(self, text):
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        n = len(payload)
        header = bytearray([0x81])  # FIN + text
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv_text(self):
        """读一帧，返回 (opcode, text)。ping 自动回 pong。"""
        while True:
            b1, b2 = self._recv_exact(2)
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._recv_exact(8))[0]
            mask_key = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length)
            if masked:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
            if opcode == 0x9:  # ping
                self.sock.sendall(bytes([0x8A, 0x80]) + b"\x00\x00\x00\x00" + payload[:0])
                continue
            if opcode == 0x1:  # text
                return payload.decode("utf-8")
            # 0x8 close 等：直接结束
            raise RuntimeError(f"WebSocket opcode {opcode}")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self._id = 0
        self.events = []

    def call(self, method, params=None, timeout=30):
        self._id += 1
        mid = self._id
        self.ws.send_text(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"CDP {method} 超时")
            self.ws.sock.settimeout(remaining)
            try:
                msg = json.loads(self.ws.recv_text())
            except Exception:
                raise
            if msg.get("id") == mid:
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)

    def drain_events(self):
        try:
            while True:
                self.ws.sock.settimeout(0.2)
                msg = json.loads(self.ws.recv_text())
                if "method" in msg:
                    self.events.append(msg)
        except Exception:
            pass

    def wait_event(self, method, timeout=20):
        deadline = time.time() + timeout
        while True:
            for i, e in enumerate(self.events):
                if e.get("method") == method:
                    return self.events.pop(i)
            remaining = deadline - time.time()
            if remaining <= 0:
                return None
            self.ws.sock.settimeout(remaining)
            try:
                msg = json.loads(self.ws.recv_text())
            except Exception:
                return None
            if "method" in msg:
                self.events.append(msg)


def find_browser(browser):
    candidates = []
    if browser in ("edge", "msedge"):
        candidates = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]
    else:
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def get_pages(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=10) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser(description="首次初始化（CDP，无 Playwright）")
    ap.add_argument("--browser", default="chrome", choices=["chrome", "msedge", "edge"])
    ap.add_argument("--profile", default=os.path.join(HERE, "browser_profile"))
    ap.add_argument("--port", type=int, default=9222)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    exe = find_browser(args.browser)
    if not exe:
        print("[失败] 未找到浏览器，请安装 Chrome 或 Edge。")
        return 1

    os.makedirs(args.profile, exist_ok=True)

    proc = subprocess.Popen([
        exe,
        f"--remote-debugging-port={args.port}",
        f"--user-data-dir={args.profile}",
        "--no-first-run",
        "--no-default-browser-check",
        DOUBAO_URL,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 等待 CDP 就绪
    pages = None
    for _ in range(60):
        try:
            pages = get_pages(args.port)
            break
        except Exception:
            time.sleep(0.5)
    if not pages:
        print("[失败] CDP 未就绪。")
        proc.terminate()
        return 1

    # 找 doubao 页面（type=page），拿 WebSocket URL
    page = next((p for p in pages if p.get("type") == "page" and "doubao.com" in p.get("url", "")),
                next((p for p in pages if p.get("type") == "page"), None))
    if not page:
        print("[失败] 未找到页面。")
        proc.terminate()
        return 1

    ws = WS(page["webSocketDebuggerUrl"])
    cdp = CDP(ws)
    cdp.call("Network.enable")
    cdp.call("Runtime.enable")

    captured = {"strData": None}

    # 登录等待
    def logged_in():
        r = cdp.call("Runtime.evaluate", {
            "expression": "localStorage.getItem('xmst') || localStorage.getItem('flow_web_has_login') === 'true'",
            "returnByValue": True,
        })
        return bool(r.get("result", {}).get("value"))

    if not logged_in():
        print("\n请在浏览器里登录 doubao.com（扫码/手机号）。")
        print("登录完成后回终端按回车继续...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

    # 重新加载，触发 /web/r/token（mssdk 初始化），并拦截 strData
    print("重载页面以触发设备指纹采集...")
    cdp.call("Page.enable")
    cdp.call("Page.reload")
    deadline = time.time() + 20
    while time.time() < deadline:
        ev = cdp.wait_event("Network.requestWillBeSent", timeout=20)
        if not ev:
            break
        url = ev.get("params", {}).get("request", {}).get("url", "")
        if "web/r/token" in url:
            try:
                body = json.loads(ev["params"]["request"].get("postData", "{}"))
                if body.get("strData"):
                    captured["strData"] = body["strData"]
                    break
            except Exception:
                pass

    # 抓 cookies（含 HttpOnly）
    cookies = {}
    r = cdp.call("Network.getAllCookies")
    for c in r.get("cookies", []):
        if "doubao.com" in c.get("domain", ""):
            cookies[c["name"]] = c["value"]

    # 抓 localStorage
    r = cdp.call("Runtime.evaluate", {
        "expression": "(() => { const o = {}; for (let i=0;i<localStorage.length;i++){const k=localStorage.key(i);o[k]=localStorage.getItem(k);} return o; })()",
        "returnByValue": True,
    })
    ls = r.get("result", {}).get("value", {}) or {}

    r = cdp.call("Runtime.evaluate", {"expression": "navigator.userAgent", "returnByValue": True})
    ua = r.get("result", {}).get("value", "")

    def get_json(s):
        try:
            return json.loads(s)
        except Exception:
            return {}

    web_id = get_json(ls.get("__tea_cache_tokens_497858", "")).get("web_id", "")
    device_id = get_json(ls.get("samantha_web_web_id", "")).get("web_id", "")
    fp = cookies.get("s_v_web_id", "")
    doubao_uid = ls.get("flow_tea_user_id", "")
    xmst = ls.get("xmst", "")

    ws.close()
    proc.terminate()

    if not cookies.get("sessionid") and not cookies.get("sessionid_ss"):
        print("[失败] 未抓到会话 cookie，请确认已登录后重试。")
        return 1
    if not captured["strData"]:
        print("[失败] 未捕获到设备指纹 strData，请重试。")
        return 1

    try:
        fingerprint = mssdk.b64_s1_decode(captured["strData"])
        key = fingerprint[1]
        fingerprint = json.loads(mssdk.rc4(bytes([key]), fingerprint[2:]).decode("utf-8"))
    except Exception as e:
        print(f"[失败] 指纹解密出错：{e}")
        return 1

    device = dict(CONST_DEVICE)
    device.update({
        "web_id": web_id,
        "tea_uuid": web_id,
        "device_id": device_id,
        "web_tab_id": str(uuid.uuid4()),
        "fp": fp,
        "user_agent": ua,
    })
    identity = {
        "cookies": cookies,
        "device": device,
        "user": {"doubao_uid": doubao_uid, "bot_id": BOT_ID},
        "xmst": xmst,
        "captured": {"a_bogus": "", "msToken": xmst, "note": "由 setup_login.py(CDP) 生成"},
    }
    with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
        json.dump(identity, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(FINGERPRINT_FILE, "w", encoding="utf-8") as f:
        json.dump(fingerprint, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("\n[成功] 已生成 doubao_identity.json + fingerprint_template.json")
    print(f"  账号 uid  = {doubao_uid}")
    print(f"  web_id    = {web_id}")
    print(f"  device_id = {device_id}")
    print("\n现在可以运行：python doubao_chat.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
