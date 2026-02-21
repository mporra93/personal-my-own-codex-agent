# syntax=docker/dockerfile:1
FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Install OpenCode CLI (must run with bash — installer uses [[ syntax)
RUN curl -fsSL https://opencode.ai/install | bash \
    && OPENCODE_BIN=$(find /root /usr/local -name "opencode" -type f 2>/dev/null | head -1) \
    && echo "opencode binary found at: $OPENCODE_BIN" \
    && test -n "$OPENCODE_BIN" \
    && ln -sf "$OPENCODE_BIN" /usr/local/bin/opencode

# Verify installation
RUN /usr/local/bin/opencode --version

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
