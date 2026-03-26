#!/usr/bin/env python3
"""Reverse proxy for Torrentio that routes through SOCKS5 tunnel"""
import http.server
import urllib.request
import socks
import socket
import ssl
import json

LISTEN_PORT = 8765
SOCKS_HOST = '127.0.0.1'
SOCKS_PORT = 1080
TARGET = 'https://torrentio.strem.fun'

# Set up SOCKS proxy for all socket connections
socks.set_default_proxy(socks.SOCKS5, SOCKS_HOST, SOCKS_PORT)
socket.socket = socks.socksocket

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = TARGET + self.path
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url)
            for key, val in self.headers.items():
                if key.lower() not in ('host', 'connection'):
                    req.add_header(key, val)
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                body = resp.read()
                self.send_response(resp.status)
                for key, val in resp.headers.items():
                    if key.lower() not in ('transfer-encoding', 'connection'):
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(body)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logs

print(f'Torrentio proxy listening on 0.0.0.0:{LISTEN_PORT}')
server = http.server.HTTPServer(('0.0.0.0', LISTEN_PORT), ProxyHandler)
server.serve_forever()
