#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解密 strData（临时分析脚本）"""
import json, base64, sys

s1 = 'Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe'
std = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
trans = str.maketrans(s1, std)


def rc4(key: bytes, data: bytes) -> bytes:
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


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    path = sys.argv[1] if len(sys.argv) > 1 else 'strData.json'
    d = json.load(open(path, encoding='utf-8'))
    s = d['strData']
    s += '=' * (-len(s) % 4)
    raw = base64.b64decode(s.translate(trans))
    print('decoded bytes =', len(raw))
    print('first bytes hex =', raw[:4].hex(' '))
    key = raw[1]
    print('key byte =', key, '(0x%02x)' % key)
    data = raw[2:]
    plain = rc4(bytes([key]), data)
    print('plaintext =')
    print(plain.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    main()
