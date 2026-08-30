#!/usr/bin/env python3
"""Tiny, authenticated MCP-like HTTP runner for a single Actions job."""
import json, os, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("WORKSPACE", "/workspace")).resolve()
TOKEN = os.environ["MCP_TOKEN"]
MAX_OUTPUT = 200_000

def safe_path(value):
    p = (ROOT / value).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError("path outside workspace")
    return p

def result(text, error=False):
    return {"content": [{"type": "text", "text": text}], "isError": error}

def call_tool(name, args):
    if name == "list_files":
        base = safe_path(args.get("path", "."))
        limit = min(max(int(args.get("limit", 200)), 1), 1000)
        files = []
        for p in base.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                files.append(str(p.relative_to(ROOT)))
                if len(files) >= limit:
                    break
        return result("\n".join(files) or "(no files)")
    if name == "search_files":
        import re
        pattern = args.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("search_files requires a non-empty pattern")
        base = safe_path(args.get("path", "."))
        rx = re.compile(pattern)
        matches, limit = [], min(max(int(args.get("limit", 100)), 1), 500)
        for p in base.rglob("*"):
            if not p.is_file() or ".git" in p.parts:
                continue
            try: lines = p.read_text(errors="ignore").splitlines()
            except OSError: continue
            for number, line in enumerate(lines, 1):
                if rx.search(line):
                    matches.append(f"{p.relative_to(ROOT)}:{number}:{line[:500]}")
                    if len(matches) >= limit: return result("\n".join(matches))
        return result("\n".join(matches) or "(no matches)")
    if name == "exec":
        argv = args.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError("exec requires a non-empty argv string array")
        timeout = min(max(int(args.get("timeout", 120)), 1), 300)
        cwd = safe_path(args.get("cwd", "."))
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout + p.stderr)[-MAX_OUTPUT:]
        return result(f"exit={p.returncode}\n{out}", p.returncode != 0)
    if name == "read_file":
        p = safe_path(args["path"])
        return result(p.read_text()[-MAX_OUTPUT:])
    if name == "write_file":
        p = safe_path(args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"])
        return result(f"wrote {p.relative_to(ROOT)}")
    raise ValueError(f"unknown tool: {name}")

TOOLS = [
    {"name": "list_files", "description": "List workspace files.", "inputSchema": {"type":"object", "properties":{"path":{"type":"string"},"limit":{"type":"integer"}}}},
    {"name": "search_files", "description": "Search text files with a regular expression.", "inputSchema": {"type":"object", "properties":{"pattern":{"type":"string"},"path":{"type":"string"},"limit":{"type":"integer"}}, "required":["pattern"]}},
    {"name": "exec", "description": "Run a command without a shell inside the workspace.", "inputSchema": {"type":"object", "properties":{"argv":{"type":"array","items":{"type":"string"}},"cwd":{"type":"string"},"timeout":{"type":"integer"}}, "required":["argv"]}},
    {"name": "read_file", "description": "Read a workspace file.", "inputSchema": {"type":"object", "properties":{"path":{"type":"string"}}, "required":["path"]}},
    {"name": "write_file", "description": "Write a workspace file.", "inputSchema": {"type":"object", "properties":{"path":{"type":"string"},"content":{"type":"string"}}, "required":["path","content"]}},
]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health": self.send_json(200, {"status":"ok"})
        else: self.send_error(404)
    def do_POST(self):
        if self.path != "/mcp" or self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.send_json(401, {"jsonrpc":"2.0","error":{"code":-32001,"message":"Unauthorized"},"id":None}); return
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 2_000_000)))
            method, ident = body.get("method"), body.get("id")
            if method == "initialize": value = {"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"cloudrun","version":"1.0"}}
            elif method == "notifications/initialized": return self.send_json(202, {})
            elif method == "tools/list": value = {"tools": TOOLS}
            elif method == "tools/call": value = call_tool(body["params"]["name"], body["params"].get("arguments", {}))
            else: raise ValueError(f"unknown method: {method}")
            self.send_json(200, {"jsonrpc":"2.0","id":ident,"result":value})
        except subprocess.TimeoutExpired: self.send_json(200, {"jsonrpc":"2.0","id":body.get("id"),"result":result("command timed out", True)})
        except Exception as e: self.send_json(200, {"jsonrpc":"2.0","id":body.get("id"),"result":result(str(e), True)})
    def send_json(self, code, value):
        data = json.dumps(value).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *_): pass

ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
