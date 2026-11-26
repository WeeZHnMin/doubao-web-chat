#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多轮对话实测：同一 conversation 连发两条消息。"""
import sys
import doubao_chat as m

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    identity = m.Identity()
    ms = identity.data.get("xmst", "")
    signer = m.PythonAbogusSigner(ms_token_provider=ms)
    chat = m.DoubaoChat(identity, signer)
    try:
        r1 = chat.send("第一轮：记住数字 42")
        print(f"[T1] conv={chat.conversation_id} ai_index={r1['meta'].get('ai_index')} reply={r1['text'][:50]!r}")
        r2 = chat.send("第二轮：我上一句说的数字是多少？")
        print(f"[T2] conv={chat.conversation_id} ai_index={r2['meta'].get('ai_index')} reply={r2['text'][:120]!r}")
        print("多轮状态：", "OK" if r1['meta'].get('ai_index') and r2['meta'].get('ai_index') else "FAIL")
    finally:
        signer.close()

if __name__ == "__main__":
    main()
