#!/usr/bin/env python3
"""Static server for the local renderer with two extras: GET /scene?path= reads a .excalidraw from
disk, POST /save?path= writes the exported PNG; binds 127.0.0.1 only."""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("EXCALIDRAW_LOCAL_PORT", "7331"))


class Handler(SimpleHTTPRequestHandler):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, directory=ROOT, **kwargs)

	def log_message(self, *_):
		return

	def _query(self):
		return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

	def do_GET(self):
		if urlparse(self.path).path == "/scene":
			path = self._query().get("path", "")
			if not (path.endswith(".excalidraw") and os.path.isfile(path)):
				return self._reply(404, b"no such scene")
			body = open(path, "rb").read()
			json.loads(body)  # refuse to serve something that is not JSON
			return self._reply(200, body, "application/json")
		if urlparse(self.path).path == "/":
			self.path = "/index.html"
		return super().do_GET()

	def do_POST(self):
		if urlparse(self.path).path != "/save":
			return self._reply(404, b"unknown")
		path = self._query().get("path", "")
		if not path.endswith(".png"):
			return self._reply(400, b"path must end in .png")
		length = int(self.headers.get("Content-Length", "0"))
		os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
		open(path, "wb").write(self.rfile.read(length))
		return self._reply(200, b"ok")

	def _reply(self, status, body, content_type="text/plain"):
		self.send_response(status)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)


if __name__ == "__main__":
	server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
	print(f"local excalidraw on http://127.0.0.1:{PORT}", file=sys.stderr)
	server.serve_forever()
