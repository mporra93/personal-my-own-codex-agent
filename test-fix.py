#!/usr/bin/env python3
"""
test-fix.py — Quick smoke-test for the Codex Agent /fix endpoint.

Usage examples
--------------
# Minimal (no image):
  python test-fix.py \
      --repo "https://github.com/owner/repo" \
      --prompt "Fix the NullPointerException in UserService.getById()"

# With a screenshot:
  python test-fix.py \
      --repo "https://github.com/owner/repo" \
      --prompt "The login button is misaligned on mobile" \
      --image screenshot.png

# Override the base URL (default http://localhost:8000):
  python test-fix.py --base-url http://192.168.1.10:8000 ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests  # pip install requests


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a test bug-fix request to the Codex Agent API.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the running Codex Agent API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="HTTPS GitHub repository URL, e.g. https://github.com/owner/repo",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Bug description / prompt to send to the agent",
    )
    parser.add_argument(
        "--image",
        default=None,
        help="Path to a local image file (PNG/JPEG) to attach as evidence (optional)",
    )
    args = parser.parse_args()

    # ── Health check ──────────────────────────────────────────────────
    health_url = f"{args.base_url.rstrip('/')}/health"
    print(f"[*] Checking health at {health_url} …")
    try:
        resp = requests.get(health_url, timeout=5)
        resp.raise_for_status()
        print(f"[✓] Health OK: {resp.json()}")
    except requests.RequestException as exc:
        print(f"[✗] Health check failed: {exc}")
        print("    Make sure the server is running (docker compose up --build)")
        sys.exit(1)

    # ── Prepare multipart payload ─────────────────────────────────────
    fix_url = f"{args.base_url.rstrip('/')}/fix"

    data = {
        "repo_url": args.repo,
        "bug_description": args.prompt,
    }

    files = {}
    if args.image:
        img_path = Path(args.image)
        if not img_path.is_file():
            print(f"[✗] Image file not found: {img_path}")
            sys.exit(1)

        # Detect MIME type from extension
        suffix = img_path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime = mime_map.get(suffix, "application/octet-stream")
        files["image"] = (img_path.name, img_path.open("rb"), mime)
        print(f"[*] Attaching image: {img_path}  ({mime})")

    # ── Send POST /fix ────────────────────────────────────────────────
    print(f"[*] POST {fix_url}")
    print(f"    repo_url        = {args.repo}")
    print(f"    bug_description = {args.prompt}")
    print(f"    image           = {args.image or '(none)'}")
    print()

    try:
        resp = requests.post(fix_url, data=data, files=files if files else None, timeout=660)
    except requests.RequestException as exc:
        print(f"[✗] Request failed: {exc}")
        sys.exit(1)

    # ── Output result ─────────────────────────────────────────────────
    print(f"[*] HTTP {resp.status_code}")
    try:
        body = resp.json()
        print(json.dumps(body, indent=2, ensure_ascii=False))
    except ValueError:
        print(resp.text)

    if resp.status_code in (200, 201):
        print("\n[✓] Success!")
    else:
        print(f"\n[✗] Failed with status {resp.status_code}")
        sys.exit(1)


if __name__ == "__main__":
    main()
