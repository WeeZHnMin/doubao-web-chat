#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流式传输可视化验收：每个文本块带上到达时间戳，证明是边收边出。"""
import sys
import time
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
        t0 = time.time()
        print("流式发送「请用三句话介绍你自己」，观察每个块的到达时间：\n")
        n = 0
        for chunk in chat.stream("请用三句话介绍你自己"):
            n += 1
            dt = time.time() - t0
            print(f"[{dt:7.3f}s] 第{n:2d}块: {chunk!r}", flush=True)
        print(f"\n共 {n} 个文本块，总耗时 {time.time()-t0:.3f}s")
        print("✅ 若上面每块的时间戳不同、逐行出现，说明就是流式传输。")
    finally:
        signer.close()


if __name__ == "__main__":
    main()
