#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性本地接收器：把 POST body 写到指定文件。"""
import http.server
import sys

OUT = sys.argv[1]
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        with open(OUT, "wb") as f:
            f.write(data)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


print(f"listening on 127.0.0.1:{PORT} -> {OUT}", flush=True)
http.server.HTTPServer(("127.0.0.1", PORT), H).serve_forever()
