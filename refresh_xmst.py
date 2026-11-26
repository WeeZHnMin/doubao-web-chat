#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_xmst.py — 纯 Python 刷新 msToken（独立命令行工具）

原理：mssdk.refresh_ms_token() 现场生成 strData → /web/r/token → 回填 identity.json。
注意：doubao_chat.py 发消息失败时会自动调用同一刷新逻辑，无需手动跑本脚本；
      本脚本仅供手动主动刷新 token 使用。
"""
import json
import os
import sys

import mssdk

HERE = os.path.dirname(os.path.abspath(__file__))
IDENTITY_FILE = os.path.join(HERE, "doubao_identity.json")
FINGERPRINT_FILE = os.path.join(HERE, "fingerprint_template.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")


def refresh() -> int:
    try:
        token = mssdk.refresh_ms_token(UA, FINGERPRINT_FILE)
    except Exception as e:
        print(f"[失败] {e}")
        return 1

    if not token:
        print("[失败] 未返回 x-ms-token")
        return 1

    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["xmst"] = token
    data.setdefault("captured", {})["msToken"] = token
    with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[成功] 已刷新并回填 msToken 到 {IDENTITY_FILE}")
    print(f"       x-ms-token = {token[:50]}...")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(refresh())
