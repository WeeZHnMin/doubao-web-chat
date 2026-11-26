#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mssdk.py — mssdk strData 生成（逆向实现，纯 Python，无浏览器）

逆向结论（见 mssdk-msToken-mechanism.md）：
    strData = base64_s1('A' + key + RC4(key, JSON.stringify(指纹对象)))
  - key 是 1 字节随机数
  - RC4 是标准 RC4（区别于 a_bogus 用的 RC4-like）
  - base64 使用自定义字母表 s1（区别于标准 base64）
"""
import base64
import json
import random
import time
import urllib.request

MSSDK_URL = "https://mssdk.bytedance.com/web/r/token?ms_appid=497858"

S1 = 'Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe'
STD = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
_TO_S1 = str.maketrans(STD, S1)
_FROM_S1 = str.maketrans(S1, STD)


def rc4(key: bytes, data: bytes) -> bytes:
    """标准 RC4"""
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    i = j = 0
    out = bytearray()
    for b in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        out.append(b ^ S[(S[i] + S[j]) % 256])
    return bytes(out)


def b64_s1_encode(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii').translate(_TO_S1)


def b64_s1_decode(s: str) -> bytes:
    s += '=' * (-len(s) % 4)
    return base64.b64decode(s.translate(_FROM_S1))


def generate_strdata(fp: dict) -> str:
    """等价于 bdms 里的 Nt(JSON.stringify(fp))。"""
    key = random.randint(0, 255)
    plain = json.dumps(fp, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    payload = b'A' + bytes([key]) + rc4(bytes([key]), plain)
    return b64_s1_encode(payload)


def load_fingerprint(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def refresh_ms_token(ua: str, fingerprint_path: str) -> str:
    """纯 HTTP 刷新 msToken：现场生成 strData → /web/r/token → 返回 x-ms-token。"""
    fp = load_fingerprint(fingerprint_path)
    str_data = generate_strdata(fp)
    body = {
        "magic": 538969122,
        "version": 1,
        "dataType": 8,
        "strData": str_data,
        "tspFromClient": int(time.time() * 1000),
        "ulr": 0,
    }
    req = urllib.request.Request(MSSDK_URL, method="POST")
    req.add_header("Content-Type", "text/plain;charset=UTF-8")
    req.add_header("User-Agent", ua)
    req.add_header("Referer", "https://www.doubao.com/")
    req.data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.headers.get("x-ms-token")


if __name__ == '__main__':
    # 自检：生成一个 strData 并解密回来，验证 round-trip 正确
    fp = load_fingerprint('fingerprint_template.json')
    s = generate_strdata(fp)
    raw = b64_s1_decode(s)
    assert raw[0] == 0x41
    key = raw[1]
    dec = rc4(bytes([key]), raw[2:])
    back = json.loads(dec.decode('utf-8'))
    print('round-trip OK:', back['nWID']['ms_version'], list(back['nWID'].keys()))
    print('strData sample:', s[:60], '... len', len(s))
