#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
abogus_py.py — a_bogus 算法的 Python 翻译
对应 A-Bogus-Reverse/abogus.js + deps.js（bdms 1.0.1.19/1.0.1.20 家族）
注意：严格复刻 JS 的 ToInt32 / >>0 / encodeURIComponent / 自定义 base64 语义。
"""
import base64
import random
import re
import time
import urllib.parse

M_727 = "dhzx"
_STD = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'


def _js_shr0(x):
    """JS 的 x >> 0：ToInt32（截断向零 + mod 2^32 + 有符号）。"""
    x = int(x) % 0x100000000
    if x >= 0x80000000:
        x -= 0x100000000
    return x


def _js_double_not(x):
    """JS 的 ~~x：ToNumber 后 ToInt32。'20-alpha' -> NaN -> 0，'08' -> 8。"""
    try:
        return int(float(str(x).strip()))
    except (ValueError, TypeError):
        return 0


def _rol(x, n):
    n %= 32
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# SM3
# ---------------------------------------------------------------------------
class SM3:
    def __init__(self):
        self.reset()

    def reset(self):
        self.reg = [1937774191, 1226093241, 388252375, 3666478592,
                    2842636476, 372324522, 3817729613, 2969243214]
        self.chunk = []
        self.size = 0

    @staticmethod
    def _str_bytes(t):
        enc = urllib.parse.quote(t, safe="!*'()")
        out = bytearray()
        i = 0
        while i < len(enc):
            if enc[i] == '%' and i + 2 < len(enc):
                out.append(int(enc[i + 1:i + 3], 16))
                i += 3
            else:
                out.append(ord(enc[i]))
                i += 1
        return list(out)

    def write(self, t):
        r = self._str_bytes(t) if isinstance(t, str) else list(t)
        self.size += len(r)
        e = 64 - len(self.chunk)
        if len(r) < e:
            self.chunk.extend(r)
        else:
            self.chunk.extend(r[:e])
            while len(self.chunk) >= 64:
                self._compress(self.chunk)
                self.chunk = r[e:min(e + 64, len(r))] if e < len(r) else []
                e += 64

    def sum(self, t=None, r=None):
        if t is not None:
            self.reset()
            self.write(t)
        self._fill()
        for e in range(0, len(self.chunk), 64):
            self._compress(self.chunk[e:e + 64])
        if r == 'hex':
            u = ''.join(f'{x:08x}' for x in self.reg)
        else:
            u = [0] * 32
            for e in range(8):
                s = self.reg[e]
                u[4 * e + 3] = s & 255
                u[4 * e + 2] = (s >> 8) & 255
                u[4 * e + 1] = (s >> 16) & 255
                u[4 * e] = (s >> 24) & 255
        self.reset()
        return u

    def _compress(self, t):
        r = [0] * 132
        for e in range(16):
            r[e] = ((t[4 * e] << 24) | (t[4 * e + 1] << 16) |
                    (t[4 * e + 2] << 8) | t[4 * e + 3]) & 0xFFFFFFFF
        for n in range(16, 68):
            o = r[n - 16] ^ r[n - 9] ^ _rol(r[n - 3], 15)
            o = o ^ _rol(o, 15) ^ _rol(o, 23)
            r[n] = (o ^ _rol(r[n - 13], 7) ^ r[n - 6]) & 0xFFFFFFFF
        for n in range(64):
            r[n + 68] = (r[n] ^ r[n + 4]) & 0xFFFFFFFF
        e = self.reg[:]
        for n in range(64):
            tj = 2043430169 if n < 16 else 2055708042
            o = (_rol(e[0], 12) + e[4] + _rol(tj, n)) & 0xFFFFFFFF
            o = _rol(o, 7)
            i = o ^ _rol(e[0], 12)
            if n < 16:
                ff = (e[0] ^ e[1] ^ e[2]) & 0xFFFFFFFF
            else:
                ff = ((e[0] & e[1]) | (e[0] & e[2]) | (e[1] & e[2])) & 0xFFFFFFFF
            u = (ff + e[3] + i + r[n + 68]) & 0xFFFFFFFF
            if n < 16:
                gg = (e[4] ^ e[5] ^ e[6]) & 0xFFFFFFFF
            else:
                gg = ((e[4] & e[5]) | ((~e[4]) & e[6])) & 0xFFFFFFFF
            s = (gg + e[7] + o + r[n]) & 0xFFFFFFFF
            e[3] = e[2]
            e[2] = _rol(e[1], 9)
            e[1] = e[0]
            e[0] = u
            e[7] = e[6]
            e[6] = _rol(e[5], 19)
            e[5] = e[4]
            e[4] = (s ^ _rol(s, 9) ^ _rol(s, 17)) & 0xFFFFFFFF
        for c in range(8):
            self.reg[c] = (self.reg[c] ^ e[c]) & 0xFFFFFFFF

    def _fill(self):
        t = 8 * self.size
        self.chunk.append(0x80)
        r = len(self.chunk) % 64
        if 64 - r < 8:
            r -= 64
        while r < 56:
            self.chunk.append(0)
            r += 1
        for e in range(4):
            n = t // 4294967296
            self.chunk.append((n >> (8 * (3 - e))) & 255)
        for e in range(4):
            self.chunk.append((t >> (8 * (3 - e))) & 255)


# ---------------------------------------------------------------------------
# RC4-like / Base64-like
# ---------------------------------------------------------------------------
def rc4_like(key, data):
    """改造版 RC4（KSA 用乘法项）。key/data 为 str（每字符 0-255），返回 str。"""
    v0 = [0] * 256
    for i in range(256):
        v0[255 - i] = i
    v2 = 0
    for v3 in range(256):
        v10 = (v2 * v0[v3] + v2 + ord(key[v3 % len(key)])) % 256
        v0[v3], v0[v10] = v0[v10], v0[v3]
        v2 = v10
    v4 = v5 = v6 = 0
    out = []
    while v5 < len(data):
        v8 = (v4 + 1) % 256
        v9 = (v6 + v0[v8]) % 256
        v0[v8], v0[v9] = v0[v9], v0[v8]
        out.append(ord(data[v5]) ^ v0[(v0[v8] + v0[v9]) % 256])
        v5 += 1
        v4 = v8
        v6 = v9
    return ''.join(chr(x) for x in out)


_S_ALPHABETS = {
    's0': 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',
    's1': 'Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe',
    's2': 'Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe',
    's3': 'ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe',
    's4': 'Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe',
}


def _base64_like(s, alphabet):
    alphabet = _S_ALPHABETS.get(alphabet, alphabet)
    if isinstance(s, str):
        s = s.encode('latin-1')
    std = base64.b64encode(s).decode('ascii')
    return std.translate(str.maketrans(_STD, alphabet))


# ---------------------------------------------------------------------------
# 依赖函数
# ---------------------------------------------------------------------------
def m_728(a0, a1, a2):
    key = bytes([int(a0 / 256) & 255, a0 % 256, a1 % 256]).decode('latin-1')
    return rc4_like(key, a2.strip())


def nr():
    return [0, 0, 0, 0, 129]


def m_731(a0):
    keys = list(a0.keys())
    return str(a0[keys[0]]) + ''.join('|' + str(a0[k]) for k in keys[1:])


def m_732(a0):
    out = []
    for ch in a0:
        c = ord(ch)
        if c & 0xFF00:
            out.append(c >> 8)
            out.append(c & 255)
        else:
            out.append(c)
    return out


def m_716():
    if nr()[4] & 64:
        v0 = int(random.random() * 109)
        return v0 + 110 + (v0 % 2)
    v0 = int(random.random() * 240)
    if v0 > 109:
        return v0 + (v0 % 2) + 1
    return v0


def m_718(a0, v0=0):
    v1 = int(random.random() * 65535)
    if v0 == 2:
        v2 = m_716()
        v3 = 179
    else:
        v2 = v1 & 255
        v3 = 0 if v0 == 1 else ((v1 >> 8) & 255)
    return [
        (v2 & 170) | (a0[0] & 85),
        (v2 & 85) | (a0[0] & 170),
        (v3 & 170) | (a0[1] & 85),
        (v3 & 85) | (a0[1] & 170),
    ]


def m_733(a0):
    v1 = m_718([a0[0], a0[1]])
    v0 = m_718([a0[2], a0[3]], 2)
    return v1 + v0


def m_734(a0):
    return list(a0)


def m_735(a0):
    out = []
    v1 = 0
    while v1 < len(a0):
        if v1 + 2 < len(a0):
            v4 = int(random.random() * 1000) & 255
            out.extend([
                (v4 & 145) | (a0[v1] & 110),
                (v4 & 66) | (a0[v1 + 1] & 189),
                (v4 & 44) | (a0[v1 + 2] & 211),
                (a0[v1] & 145) | (a0[v1 + 1] & 66) | (a0[v1 + 2] & 44),
            ])
        else:
            out.append(a0[v1])
            if v1 + 1 < len(a0) and a0[v1 + 1]:
                out.append(a0[v1 + 1])
        v1 += 3
    return out


# ---------------------------------------------------------------------------
# 主算法
# ---------------------------------------------------------------------------
class Abogus:
    def __init__(self, ua):
        self.ua = ua
        self.m719 = 0
        self.m730 = int(time.time() * 1000)

    def _m729(self):
        if self.m719 > 10745:
            return 3
        if self.m719 > 1283:
            return 4
        if self.m719 > 139:
            return 5
        return 6

    def calculate(self, query, body='', page_id=1, aid=497858, version='1.0.1.20-alpha.08'):
        self.m719 += 1
        v0 = 3
        v1 = int(time.time() * 1000)
        sm3 = SM3()
        v3 = 1
        v4 = 14
        v5 = sm3.sum(sm3.sum(query + M_727))
        v6 = sm3.sum(sm3.sum(body + M_727))
        v7 = sm3.sum(_base64_like(m_728(v3, v4, self.ua), 's3'))
        v8 = int(time.time() * 1000)
        v2 = [3, 82]
        v10 = int(time.time() * 1000)
        v11 = _js_shr0((v10 - float(str(v10) + '1721836800000')) / 1000 / 60 / 60 / 24 / 14) & 0xFF
        v10 = self._m729()
        v12 = (v1 - self.m730 + 3) & 255 if self.m730 > 0 else 2

        v1_32 = v1 & 0xFFFFFFFF
        v13 = v1_32 & 255
        v14 = (v1_32 >> 8) & 255
        v15 = (v1_32 >> 16) & 255
        v16 = (v1_32 >> 24) & 255
        v17 = int(v1 / 4294967296) & 255
        v18 = int(v1 / 1099511627776) & 255
        v19 = v3 % 256 & 255
        v20 = int(v3 / 256) & 255

        v3 = nr()
        v21 = v3[4] & 255
        v22 = (v3[4] >> 8) & 255
        v23 = v3[0]
        v24 = v3[1]
        v25 = v3[2]
        v26 = v3[3]
        v27 = v4 & 255
        v28 = (v4 >> 8) & 255
        v29 = (v4 >> 16) & 255
        v30 = (v4 >> 24) & 255
        v4 = v5[9]
        v31 = v5[18]
        v32 = 3
        v33 = v5[3]
        while v33 == 11:
            v63 = v32 + 1
            v33 = v5[v63] if v63 < len(v6) else 12
            v32 = v63
        v34 = 11 if (v3[4] & 2) else v33
        v35 = v6[10]
        v36 = v6[19]
        v37 = 4
        v38 = v6[4]
        while v38 == 8:
            v63 = v37 + 1
            v38 = v6[v63] if v63 < len(v6) else 9
            v37 = v63
        v39 = 8 if (v3[4] & 4) else v38
        v40 = v7[11]
        v41 = v7[21]
        v42 = 5
        v43 = v7[5]
        while v43 == 12:
            v63 = v42 + 1
            v43 = v7[v63] if v63 < len(v7) else 13
            v42 = v63
        v44 = 12 if (v3[4] & 8) else v43

        v8_32 = v8 & 0xFFFFFFFF
        v45 = v8_32 & 255
        v46 = (v8_32 >> 8) & 255
        v47 = (v8_32 >> 16) & 255
        v48 = (v8_32 >> 24) & 255
        v49 = int(v8 / 4294967296) & 255
        v50 = int(v8 / 1099511627776) & 255

        v51 = page_id & 255
        v52 = (page_id >> 8) & 255
        v53 = (page_id >> 16) & 255
        v54 = (page_id >> 24) & 255
        v55 = aid & 255
        v56 = (aid >> 8) & 255
        v57 = (aid >> 16) & 255
        v58 = (aid >> 24) & 255

        v59 = {
            'innerWidth': 1080, 'innerHeight': 1239,
            'outerWidth': 1080, 'outerHeight': 1832,
            'availWidth': 1080, 'availHeight': 1920,
            'sizeWidth': 1080, 'sizeHeight': 1920,
            'platform': "MacIntel",
        }
        v60 = m_732(m_731(v59))
        v59 = len(v60)
        v61 = v59 & 255
        v62 = (v59 >> 8) & 255
        v59 = m_732(str((v1 + 3) & 255) + ',')
        v63 = len(v59)
        v64 = v63 & 255
        v65 = (v63 >> 8) & 255

        v63 = m_733([_js_double_not(x) for x in version.split('.')])
        v66 = v63[0] ^ v63[1] ^ v63[2] ^ v63[3] ^ v63[4] ^ v63[5]
        v67 = v66 ^ v63[6] ^ v63[7] ^ 41 ^ v11 ^ v10 ^ v12
        v66 = v67 ^ v13 ^ v14 ^ v15 ^ v16 ^ v17 ^ v18 ^ v19 ^ v20
        v67 = v66 ^ v21 ^ v22 ^ v23 ^ v24 ^ v25 ^ v26 ^ v27 ^ v28
        v66 = v67 ^ v29 ^ v30 ^ v4 ^ v31 ^ v34 ^ v35 ^ v36 ^ v39
        v67 = v66 ^ v40 ^ v41 ^ v44 ^ v45 ^ v46 ^ v47 ^ v48 ^ v49
        v66 = v67 ^ v50 ^ v0 ^ v51 ^ v52 ^ v53 ^ v54 ^ v55 ^ v56

        v67 = [0] * 50
        v67[0] = v18
        v67[1] = v27
        v67[2] = v40
        v67[3] = v46
        v67[4] = v57
        v67[5] = v13
        v67[6] = v54
        v67[7] = v28
        v67[8] = v19
        v67[9] = v31
        v67[10] = v21
        v67[11] = v0
        v67[12] = v34
        v67[13] = v52
        v67[14] = v12
        v67[15] = v4
        v67[16] = v49
        v67[17] = v30
        v67[18] = v14
        v67[19] = v55
        v67[20] = v11
        v67[21] = v39
        v67[22] = v15
        v67[23] = v53
        v67[24] = v44
        v67[25] = v23
        v67[26] = v47
        v67[27] = v48
        v67[28] = v10
        v67[29] = v56
        v67[30] = v24
        v67[31] = v58
        v67[32] = v41
        v67[33] = v35
        v67[34] = v25
        v67[35] = v22
        v67[36] = v17
        v67[37] = v51
        v67[38] = v36
        v67[39] = v26
        v67[40] = v50
        v67[41] = v29
        v67[42] = v20
        v67[43] = 41
        v67[44] = v45
        v67[45] = v16
        v67[46] = v61
        v67[47] = v62
        v67[48] = v64
        v67[49] = v65

        v46 = [v66 ^ v57 ^ v58 ^ v61 ^ v62 ^ v64 ^ v65]
        v52 = [
            m_734(v63),
            m_734(m_735(v67 + m_734(v60) + m_734(v59) + v46)),
        ]
        v63 = rc4_like(chr(211), ''.join(chr(x) for x in v52[0] + v52[1]))
        v52 = _base64_like(''.join(chr(x) for x in m_718(v2, 1)) + v63, 's4')
        return v52
