# personal-my-own-codex-agent

Autonomous AI-powered GitHub code-fixing agent. A FastAPI service that receives
bug reports (with optional screenshots) and autonomously clones a repository,
applies AI-generated fixes via OpenCode CLI, and opens a professional Pull Request
— fully headless inside Docker.

## Architecture

```
[Frontend]
     |
     v
[FastAPI  POST /fix]
     |
     v
[Isolated Temp Workspace]
     |
     v
[OpenCode CLI  (OpenAI model)]
     |
     v
[GitHub Repo → Branch → PR]
```

## Setup

### Prerequisites
- Docker & Docker Compose
- GitHub personal access token with `repo` + `pull_request` write scopes
- OpenAI API key

### Configuration

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key |
| `GITHUB_TOKEN` | ✅ | — | GitHub token (repo + PR scope) |
| `OPENAI_MODEL` | | `gpt-4o` | Model passed to OpenCode |
| `GIT_AUTHOR_NAME` | | `codex-agent` | Commit author name |
| `GIT_AUTHOR_EMAIL` | | `codex-agent@example.com` | Commit author email |
| `MAX_REPO_SIZE_MB` | | `500` | Repo size safety limit |
| `CLONE_TIMEOUT` | | `120` | Git clone timeout (seconds) |
| `OPENCODE_TIMEOUT` | | `600` | OpenCode run timeout (seconds) |
| `GIT_PUSH_TIMEOUT` | | `120` | Git push timeout (seconds) |

## Usage

### 1. Start the backend

First time (builds the Docker image):
```bash
docker compose up --build
```

Subsequent runs (no rebuild needed unless code changes):
```bash
docker compose up
```

The API will be available at `http://localhost:8000`. Keep this terminal open — logs from the agent will appear here.

---

### 2. Send a fix request

In a **second terminal**, use `test-fix.py` to send a request. First install the dependency if you haven't:

```bash
pip install requests
```

#### From PowerShell

Without image:
```powershell
python test-fix.py --repo "https://github.com/owner/repo" --prompt "Describe the change you want here"
```

With image:
```powershell
python test-fix.py --repo "https://github.com/owner/repo" --prompt "Describe the change you want here" --image "C:\path\to\screenshot.jpg"
```

#### From WSL / bash

Without image:
```bash
python test-fix.py --repo "https://github.com/owner/repo" --prompt "Describe the change you want here"
```

With image:
```bash
python test-fix.py --repo "https://github.com/owner/repo" --prompt "Describe the change you want here" --image "/mnt/c/path/to/screenshot.jpg"
```

> **Tip:** The more specific the prompt, the better. Include the file name, current text, and what you want to change. Example:
> `"In index.html, change the page title from 'My App' to 'My Awesome App'"`

#### Using curl directly

```bash
curl -X POST http://localhost:8000/fix \
  -F "repo_url=https://github.com/owner/repo" \
  -F "bug_description=Describe the change you want here" \
  -F "image=@/path/to/screenshot.jpg"
```

---

### 3. Check the result

**Successful response:**
```json
{
  "status": "ok",
  "pr_url": "https://github.com/owner/repo/pull/42",
  "branch": "auto/fix-1740000000"
}
```

**No changes detected** (OpenCode ran but didn't modify anything — refine your prompt):
```json
{
  "status": "no_changes",
  "branch": "auto/fix-1740000000"
}
```

---

### Model configuration

OpenCode requires the `provider/model` format in `OPENAI_MODEL`. Examples:

| `.env` value | Description |
|---|---|
| `openai/gpt-4o` | GPT-4o (default) |
| `openai/gpt-4o-mini` | Faster, cheaper |
| `openai/gpt-5.2-codex` | Codex model |
| `anthropic/claude-3-5-sonnet` | Claude (requires `ANTHROPIC_API_KEY`) |

After changing `.env`, restart without rebuild:
```bash
docker compose down && docker compose up
```

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/fix` | Submit a bug fix request |

`POST /fix` accepts `multipart/form-data`:

- `repo_url` — HTTPS GitHub URL (required)
- `bug_description` — bug description passed verbatim to OpenCode (required)
- `image` — optional screenshot (PNG/JPEG)

## Security

- Repo URL validated against strict regex (HTTPS GitHub only)
- Repository size cap enforced before processing
- All subprocesses run with timeout guards
- Temporary workspace deleted after every run
- No secrets stored on disk
