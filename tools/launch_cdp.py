"""
launch_cdp.py — Launch Chrome with remote debugging for a CDP bridge.

Usage:
    python tools/launch_cdp.py                    # interactive menu
    python tools/launch_cdp.py deepseek           # launch DeepSeek CDP
    python tools/launch_cdp.py all                # launch all platforms
    python tools/launch_cdp.py status             # show which ports are live

Each platform gets its own Chrome profile under C:\\chrome-cdp\\PORT so
sessions are isolated and stay logged in across restarts.
"""

from __future__ import annotations
import os, sys, socket, subprocess, time, argparse
from pathlib import Path

# ── Platform registry ──────────────────────────────────────────────────────────

PLATFORMS = {
    "chatgpt":    {"port": 9224, "url": "https://chatgpt.com",              "name": "ChatGPT"},
    "gemini":     {"port": 9225, "url": "https://gemini.google.com",         "name": "Gemini Web"},
    "deepseek":   {"port": 9226, "url": "https://chat.deepseek.com",         "name": "DeepSeek"},
    "claude":     {"port": 9227, "url": "https://claude.ai/new",             "name": "Claude.ai"},
    "hf":         {"port": 9228, "url": "https://huggingface.co/chat",       "name": "HuggingFace Chat"},
    "minimax":    {"port": 9229, "url": "https://chat.minimax.io",           "name": "Minimax"},
    "mistral":    {"port": 9230, "url": "https://chat.mistral.ai",           "name": "Mistral Chat"},
    "grok":       {"port": 9231, "url": "https://x.com/i/grok",             "name": "Grok (X)"},
    "kimi":       {"port": 9232, "url": "https://www.kimi.com/?chat_enter_method=new_chat", "name": "Kimi (Moonshot)"},
}

# Aliases
ALIASES = {
    "huggingface": "hf", "hfchat": "hf", "hf-chat": "hf",
    "chatgpt": "chatgpt", "gpt": "chatgpt",
    "ds": "deepseek",
    "grok": "grok", "x": "grok",
    "moonshot": "kimi", "kimi-cdp": "kimi",
}

_DATA_DIR = Path(r"C:\chrome-cdp")

# ── Chrome detection ───────────────────────────────────────────────────────────

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{user}\AppData\Local\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

def _find_chrome() -> str | None:
    user = os.environ.get("USERNAME", "")
    for p in _CHROME_PATHS:
        resolved = Path(p.replace("{user}", user))
        if resolved.exists():
            return str(resolved)
    # Try PATH
    for exe in ("chrome.exe", "google-chrome", "chromium.exe"):
        try:
            result = subprocess.run(["where", exe], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().splitlines()[0]
        except Exception:
            pass
    return None

# ── Port check ─────────────────────────────────────────────────────────────────

def _port_live(port: int) -> bool:
    try:
        s = socket.create_connection(("localhost", port), timeout=1)
        s.close()
        return True
    except Exception:
        return False

# ── Launch ────────────────────────────────────────────────────────────────────

def launch(key: str, chrome: str) -> bool:
    key = ALIASES.get(key, key)
    if key not in PLATFORMS:
        print(f"  Unknown platform: {key!r}  (known: {', '.join(PLATFORMS)})")
        return False

    p = PLATFORMS[key]
    port, url, name = p["port"], p["url"], p["name"]
    profile_dir = _DATA_DIR / str(port)
    profile_dir.mkdir(parents=True, exist_ok=True)

    if _port_live(port):
        print(f"  {name}: already live on port {port}")
        return True

    print(f"  Launching {name} on port {port} -> {url}")
    subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    # Wait up to 8s for CDP to become reachable
    for _ in range(16):
        time.sleep(0.5)
        if _port_live(port):
            print(f"  {name}: CDP ready on port {port}")
            return True
    print(f"  {name}: launched (CDP not yet reachable — log in then try again)")
    return False

# ── Status ────────────────────────────────────────────────────────────────────

def show_status():
    print(f"\n  {'PLATFORM':<16} {'PORT':<6} {'STATUS'}")
    print("  " + "-" * 40)
    for key, p in PLATFORMS.items():
        live = _port_live(p["port"])
        status = "[LIVE]   " if live else "[offline]"
        print(f"  {p['name']:<16} {p['port']:<6} {status}")
    print()

# ── Interactive menu ──────────────────────────────────────────────────────────

def interactive(chrome: str):
    print("\n  CDP Platform Launcher\n  " + "=" * 30)
    show_status()
    print("  Platforms:")
    for i, (key, p) in enumerate(PLATFORMS.items(), 1):
        live = "[live]" if _port_live(p["port"]) else ""
        print(f"  {i}. {p['name']:<18} port {p['port']}  {live}")
    print("  a. Launch ALL")
    print("  q. Quit\n")

    choice = input("  Choose (1-8 / a / q): ").strip().lower()
    if choice == "q":
        return
    if choice == "a":
        for key in PLATFORMS:
            launch(key, chrome)
        return
    try:
        idx = int(choice) - 1
        key = list(PLATFORMS.keys())[idx]
        launch(key, chrome)
    except (ValueError, IndexError):
        print("  Invalid choice.")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Launch Chrome CDP sessions for LLM bridges")
    ap.add_argument("platform", nargs="?", help="Platform name or 'all' or 'status'")
    args = ap.parse_args()

    chrome = _find_chrome()
    if not chrome:
        print("ERROR: Chrome/Edge not found. Install Google Chrome or set chrome.exe on PATH.")
        sys.exit(1)

    if args.platform == "status":
        show_status()
        return

    if args.platform == "all":
        for key in PLATFORMS:
            launch(key, chrome)
        return

    if args.platform:
        launch(args.platform, chrome)
        return

    # No arg — interactive menu
    interactive(chrome)


if __name__ == "__main__":
    main()
