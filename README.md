# personal-my-own-codex-agent
Autonomous AI-powered GitHub code editing service. It exposes a FastAPI endpoint that turns bug reports (with optional screenshots) into real pull requests. The system clones a repo, creates a branch, uses OpenCode with OpenAI to apply fixes, pushes changes, and opens a PR — fully headless inside Docker.
