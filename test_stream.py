#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流式传输验收：边收边打印（打字机效果）。"""
import sys
import doubao_chat as m


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    identity = m.Identity()
    signer = m.PythonAbogusSigner(ms_token_provider=identity.data.get("xmst", ""))
    chat = m.DoubaoChat(identity, signer)
    try:
        print("流式发送「请用一句话介绍你自己」：")
        print("豆包 > ", end="", flush=True)
        n = 0
        for chunk in chat.stream("请用一句话介绍你自己"):
            print(chunk, end="", flush=True)
            n += 1
        print()
        print(f"\n共收到 {n} 个文本块；conv={chat.conversation_id}")
        print("流式传输：OK" if n > 0 else "流式传输：FAIL")
    finally:
        signer.close()


if __name__ == "__main__":
    main()
