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

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`.

### Example request

```bash
curl -X POST http://localhost:8000/fix \
  -F "repo_url=https://github.com/owner/repo" \
  -F "bug_description=Fix the NullPointerException in UserService.getById()" \
  -F "image=@screenshot.png"
```

### Example response

```json
{
  "status": "ok",
  "pr_url": "https://github.com/owner/repo/pull/42",
  "branch": "auto/fix-1740000000"
}
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
