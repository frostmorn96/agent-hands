#!/usr/bin/env python3
"""Minimal agent loop: an OpenAI-compatible model + a shell and a filesystem.

The model is the brain. This file is the hands.
Env:
  LLM_BASE_URL  e.g. https://llm-proxy.frostmorn96.workers.dev/v1
  LLM_API_KEY   bearer token
  LLM_MODEL     model name (default: qwen)
  TASK          what to build
  WORKDIR       sandbox directory (default: work)
  MAX_STEPS     tool-call rounds (default: 40)
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = os.environ["LLM_BASE_URL"].rstrip("/")
KEY = os.environ["LLM_API_KEY"]
MODEL = os.environ.get("LLM_MODEL", "qwen")
TASK = os.environ["TASK"]
MAX_STEPS = int(os.environ.get("MAX_STEPS", "40"))
WORK = os.path.abspath(os.environ.get("WORKDIR", "work"))
os.makedirs(WORK, exist_ok=True)

ENDPOINT = BASE + ("/chat/completions" if BASE.endswith("/v1") else "/v1/chat/completions")

SYSTEM = (
    "You are an autonomous build agent. You have a shell and a filesystem inside a "
    "sandbox directory. Build what the user asks, actually run it, fix your own errors, "
    "and stop when it works. Use tools; do not describe what you would do. "
    "All paths are relative to the sandbox. Keep output short."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List files in the sandbox (recursive, max 200 entries).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file from the sandbox.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a text file in the sandbox.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}}, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a shell command in the sandbox. Returns stdout+stderr.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 120}},
            "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Call when the task is complete. Summarise what was built and how to run it.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string"}}, "required": ["summary"]},
    }},
]


def _safe(path: str) -> str:
    p = os.path.abspath(os.path.join(WORK, path))
    if not p.startswith(WORK):
        raise ValueError(f"path escapes sandbox: {path}")
    return p


def run_tool(name: str, args: dict) -> str:
    try:
        if name == "list_files":
            out = []
            for root, dirs, files in os.walk(WORK):
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
                for f in files:
                    out.append(os.path.relpath(os.path.join(root, f), WORK))
                    if len(out) >= 200:
                        return "\n".join(out)
            return "\n".join(out) or "(empty)"
        if name == "read_file":
            with open(_safe(args["path"]), "r", errors="replace") as fh:
                return fh.read()[:20000]
        if name == "write_file":
            p = _safe(args["path"])
            os.makedirs(os.path.dirname(p) or WORK, exist_ok=True)
            with open(p, "w") as fh:
                fh.write(args.get("content", ""))
            return f"wrote {len(args.get('content', ''))} bytes to {args['path']}"
        if name == "run_command":
            r = subprocess.run(args["command"], shell=True, cwd=WORK,
                               capture_output=True, text=True,
                               timeout=int(args.get("timeout", 120)))
            out = (r.stdout or "") + (r.stderr or "")
            return f"exit={r.returncode}\n{out[:6000]}"
        if name == "finish":
            return "DONE"
        return f"unknown tool: {name}"
    except subprocess.TimeoutExpired:
        return "command timed out"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


def chat(messages):
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": 2048,
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
        "User-Agent": "Mozilla/5.0",
    })
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def main():
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": TASK}]
    for step in range(1, MAX_STEPS + 1):
        try:
            data = chat(messages)
        except urllib.error.HTTPError as exc:
            print(f"[{step}] HTTP {exc.code}: {exc.read()[:400]!r}", flush=True)
            sys.exit(1)
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            print(f"[{step}] final: {(msg.get('content') or '')[:2000]}", flush=True)
            return
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": calls})
        for call in calls:
            fn = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            print(f"[{step}] {fn}({json.dumps(args)[:160]})", flush=True)
            result = run_tool(fn, args)
            print(f"      -> {result[:300].replace(chr(10), ' | ')}", flush=True)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            if fn == "finish":
                return
    print("max steps reached", flush=True)


if __name__ == "__main__":
    main()
