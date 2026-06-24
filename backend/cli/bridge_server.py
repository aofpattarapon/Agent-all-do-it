#!/usr/bin/env python3
"""CLI Bridge Server — runs on the HOST Mac so Docker containers can execute local CLI tools.

Docker containers (Linux) can't run macOS binaries directly.
This server accepts HTTP requests from the container and runs the command on the host.

Usage (run this on your Mac in a terminal before starting Docker):
    python3 backend/cli/bridge_server.py

Then set in docker-compose.yml environment:
    CLI_BRIDGE_URL=http://host.docker.internal:7777
"""

import asyncio
import json
import os
import pathlib
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Add this script's directory to PATH as a fallback so the 'kimi' wrapper
# script can be found when the official Kimi Code CLI is not installed.
# We append (not prepend) so the official binary takes precedence.
_BRIDGE_DIR = str(pathlib.Path(__file__).parent.resolve())
os.environ["PATH"] = f"{os.environ.get('PATH', '')}:{_BRIDGE_DIR}"


class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[bridge] {self.address_string()} {format % args}", flush=True)

    def do_POST(self):
        if self.path == "/exec":
            self._handle_exec()
        elif self.path == "/which":
            self._handle_which()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_exec(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        args: list[str] = body.get("args", [])
        timeout: int = body.get("timeout", 300)

        if not args:
            self._json(400, {"error": "args required"})
            return

        print(f"[bridge] exec: {args[:4]}{'...' if len(args) > 4 else ''}", flush=True)
        try:
            result = asyncio.run(_run(args, timeout))
            self._json(200, result)
        except Exception as exc:
            self._json(500, {"error": str(exc), "returncode": -1, "stdout": "", "stderr": str(exc)})

    def _handle_which(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        name: str = body.get("name", "")
        if not name:
            self._json(400, {"error": "name required"})
            return
        path = shutil.which(name)
        self._json(200, {"name": name, "path": path})

    def _json(self, code: int, data: dict) -> None:
        payload = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


async def _run(args: list[str], timeout: int) -> dict:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return {"returncode": -1, "stdout": "", "stderr": f"timed out after {timeout}s"}
    return {
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7777
    server = ThreadingHTTPServer(("0.0.0.0", port), BridgeHandler)
    print(
        f"[bridge] CLI Bridge listening on 0.0.0.0:{port} (reachable from Docker via host.docker.internal:{port})",
        flush=True,
    )
    print("[bridge] Keep this running while using Docker. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[bridge] stopped", flush=True)
