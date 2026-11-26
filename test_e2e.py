#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_e2e.py — 端到端实测：Node 生成 a_bogus + 提供的 msToken + cookies 发一条真实请求。
用法： python test_e2e.py "<msToken>" ["<消息>"]
"""
import sys
import doubao_chat as m

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ms_token = sys.argv[1] if len(sys.argv) > 1 else ""
    text = sys.argv[2] if len(sys.argv) > 2 else "你好，测试"

    identity = m.Identity()
    signer = m.PythonAbogusSigner(ms_token_provider=ms_token)
    chat = m.DoubaoChat(identity, signer)

    print(f"msToken = {ms_token[:40]}...")
    try:
        r = chat.send(text)
        print("=== 成功 ===")
        print("conv:", chat.conversation_id)
        print("section:", chat.section_id)
        print("text:", r["text"][:200])
        print("a_bogus:", r["a_bogus"][:60], "...")
    except Exception as e:
        print("=== 失败 ===")
        print(type(e).__name__, str(e)[:2000])
    finally:
        signer.close()

if __name__ == "__main__":
    main()
