"""
agent_runner.py — Core automation logic.

Orchestrates: clone → branch → opencode → commit → push → PR.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

logger = logging.getLogger("agent_runner")

# ── constants ──────────────────────────────────────────────────────────────────
MAX_REPO_SIZE_MB = int(os.getenv("MAX_REPO_SIZE_MB", "500"))
COMMIT_MSG_MAX_LENGTH = 72
CLONE_TIMEOUT = int(os.getenv("CLONE_TIMEOUT", "120"))
OPENCODE_TIMEOUT = int(os.getenv("OPENCODE_TIMEOUT", "600"))
GIT_PUSH_TIMEOUT = int(os.getenv("GIT_PUSH_TIMEOUT", "120"))

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GIT_AUTHOR_NAME = os.getenv("GIT_AUTHOR_NAME", "codex-agent")
GIT_AUTHOR_EMAIL = os.getenv("GIT_AUTHOR_EMAIL", "codex-agent@example.com")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


# ── helpers ────────────────────────────────────────────────────────────────────

def _sanitize_repo_url(repo_url: str) -> str:
    """Reject non-HTTPS GitHub URLs to prevent shell injection."""
    pattern = re.compile(
        r"^https://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(\.git)?$"
    )
    if not pattern.match(repo_url):
        raise ValueError(f"Invalid or unsupported repo URL: {repo_url!r}")
    return repo_url.rstrip("/")


def _authed_url(repo_url: str) -> str:
    """Embed GITHUB_TOKEN into the clone URL for authentication."""
    return repo_url.replace("https://", f"https://x-access-token:{GITHUB_TOKEN}@")


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 60) -> str:
    """Run a subprocess, raise on non-zero exit, return stdout."""
    logger.debug("exec: %s (cwd=%s)", " ".join(cmd), cwd)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command {cmd[0]!r} failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def _run_shell(cmd: str, cwd: str | None = None, timeout: int = 60) -> str:
    """Run a shell command string, raise on non-zero exit, return stdout."""
    logger.debug("shell: %s (cwd=%s)", cmd, cwd)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=True,
        env={**os.environ},
    )
    if result.stderr:
        logger.info("stderr: %s", result.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"Shell command failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def _repo_size_ok(workspace: str) -> None:
    """Abort if the cloned repo exceeds MAX_REPO_SIZE_MB."""
    total = sum(
        f.stat().st_size
        for f in Path(workspace).rglob("*")
        if f.is_file()
    )
    mb = total / (1024 * 1024)
    if mb > MAX_REPO_SIZE_MB:
        raise ValueError(
            f"Repository size {mb:.1f} MB exceeds limit of {MAX_REPO_SIZE_MB} MB"
        )


def _get_default_branch(repo_path: str) -> str:
    """Return the name of the remote default branch."""
    out = _run(["git", "remote", "show", "origin"], cwd=repo_path, timeout=30)
    for line in out.splitlines():
        if "HEAD branch" in line:
            return line.split(":")[-1].strip()
    return "main"


def _parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub HTTPS URL."""
    clean = repo_url.rstrip("/").removesuffix(".git")
    parts = clean.rstrip("/").split("/")
    return parts[-2], parts[-1]


# ── main entry point ───────────────────────────────────────────────────────────

async def run_agent(
    repo_url: str,
    bug_description: str,
    image_bytes: bytes | None = None,
) -> dict:
    """
    Full agent pipeline. Returns a dict with PR details on success.
    Raises on any fatal error.
    """
    repo_url = _sanitize_repo_url(repo_url)
    workspace = tempfile.mkdtemp(prefix="codex_agent_")
    logger.info("workspace=%s  repo=%s", workspace, repo_url)

    try:
        # 1. Shallow clone
        authed = _authed_url(repo_url)
        repo_path = os.path.join(workspace, "repo")
        logger.info("cloning %s …", repo_url)
        _run(
            ["git", "clone", "--depth", "1", authed, repo_path],
            timeout=CLONE_TIMEOUT,
        )
        _repo_size_ok(repo_path)

        # 2. Configure git identity inside the workspace
        _run(["git", "config", "user.name", GIT_AUTHOR_NAME], cwd=repo_path)
        _run(["git", "config", "user.email", GIT_AUTHOR_EMAIL], cwd=repo_path)

        # 3. Create feature branch
        branch = f"auto/fix-{int(time.time())}"
        _run(["git", "checkout", "-b", branch], cwd=repo_path)
        logger.info("branch=%s", branch)

        # 4. Build prompt (image is passed separately as a file, not embedded)
        prompt = bug_description

        # 5. Run OpenCode CLI.
        # Write the prompt to a file to avoid exec ARG_MAX limits.
        # If an image was provided, save it to a file and pass via --image flag.
        prompt_file = os.path.join(workspace, "prompt.txt")
        with open(prompt_file, "w", encoding="utf-8") as fh:
            fh.write(prompt)

        image_flag = ""
        if image_bytes:
            image_file = os.path.join(repo_path, ".codex_screenshot.jpg")
            with open(image_file, "wb") as fh:
                fh.write(image_bytes)
            image_flag = f"-f {shlex.quote(image_file)}"
            logger.info("image saved to %s (%d bytes)", image_file, len(image_bytes))

        logger.info("running opencode …")
        opencode_cmd = (
            f"opencode run --model {shlex.quote(OPENAI_MODEL)}"
            f' "$(cat {shlex.quote(prompt_file)})"'
            f" {image_flag}"
        ).strip()
        logger.info("opencode command: %s", opencode_cmd)
        opencode_output = await asyncio.to_thread(
            _run_shell,
            opencode_cmd,
            repo_path,
            OPENCODE_TIMEOUT,
        )
        logger.info("opencode stdout:\n%s", opencode_output)

        # 6. Commit any changes
        # Remove screenshot before staging to avoid committing it
        screenshot = os.path.join(repo_path, ".codex_screenshot.jpg")
        if os.path.exists(screenshot):
            os.remove(screenshot)

        status = _run(["git", "status", "--porcelain"], cwd=repo_path)
        if not status:
            logger.warning("opencode produced no file changes — nothing to commit")
            return {"status": "no_changes", "branch": branch}

        _run(["git", "add", "-A"], cwd=repo_path)
        commit_msg = f"Auto Fix: {bug_description[:COMMIT_MSG_MAX_LENGTH]}"
        _run(["git", "commit", "-m", commit_msg], cwd=repo_path)

        # 7. Push branch
        logger.info("pushing branch %s …", branch)
        _run(
            ["git", "push", "origin", branch],
            cwd=repo_path,
            timeout=GIT_PUSH_TIMEOUT,
        )

        # 8. Open Pull Request
        owner, repo_name = _parse_owner_repo(repo_url)
        default_branch = _get_default_branch(repo_path)
        pr = await _create_pull_request(
            owner=owner,
            repo=repo_name,
            head=branch,
            base=default_branch,
            title=f"Auto Fix: {bug_description[:COMMIT_MSG_MAX_LENGTH]}",
            body=(
                "## Automated Fix\n\n"
                f"**Bug description:**\n{bug_description}\n\n"
                "_This PR was created automatically by the codex-agent._"
            ),
        )
        logger.info("PR created: %s", pr.get("html_url"))
        return {"status": "ok", "pr_url": pr["html_url"], "branch": branch}

    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        logger.info("workspace cleaned up")


async def _create_pull_request(
    owner: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
) -> dict:
    """Call GitHub REST API to open a PR."""
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set — cannot create PR")

    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": body, "head": head, "base": base}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"GitHub PR creation failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()
