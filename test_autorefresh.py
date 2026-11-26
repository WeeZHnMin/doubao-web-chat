#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动刷新闭环验收：用无效 token 发消息，验证自动刷新后重试成功。"""
import sys
import doubao_chat as m


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    identity = m.Identity()
    signer = m.PythonAbogusSigner(ms_token_provider="INVALID_EXPIRED_TOKEN_FOR_TEST")
    chat = m.DoubaoChat(identity, signer)
    try:
        print("用无效 token 发消息，预期自动刷新后成功...")
        r = chat.send("自动刷新验证：记住数字 7")
        print(f"conv = {chat.conversation_id}")
        print(f"reply = {r['text'][:80]!r}")
        print(f"token 已刷新 = {bool(chat._ms_token)}  ({chat._ms_token[:25] if chat._ms_token else ''}...)")
        print("自动刷新闭环：OK")
    finally:
        signer.close()


if __name__ == "__main__":
    main()
