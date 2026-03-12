#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# docx-agent setup script
#
# Sets up the full environment:
#   1. Python venv + dependencies
#   2. rbc_security (optional, installs if available on your network)
#   3. pymupdf (required for PDF vision ingestion)
#   4. .env file — auto-detects Postgres DSN, you only need to fill in API creds
#   5. Postgres database + pgvector + schema migration
#
# Usage:
#   bash scripts/setup.sh              # full setup
#   bash scripts/setup.sh --skip-db   # skip Postgres (do it later manually)
#   bash scripts/setup.sh --skip-venv # skip venv (already exists)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env.example"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

SKIP_DB=false
SKIP_VENV=false

for arg in "$@"; do
    case "$arg" in
        --skip-db)   SKIP_DB=true ;;
        --skip-venv) SKIP_VENV=true ;;
        --help|-h)
            echo "Usage: $0 [--skip-db] [--skip-venv]"
            exit 0 ;;
    esac
done

echo ""
echo "════════════════════════════════════════════════════════"
echo "  docx-agent setup"
echo "════════════════════════════════════════════════════════"

# ── Step 1: Virtual environment ───────────────────────────────────────────────
if [ "$SKIP_VENV" = false ]; then
    echo ""
    if [ ! -d "$VENV_DIR" ]; then
        echo "→ Creating virtual environment at .venv ..."
        python3 -m venv "$VENV_DIR"
    else
        echo "→ Virtual environment already exists."
    fi

    echo "→ Installing dependencies ..."
    "$PIP" install --quiet --upgrade pip
    "$PIP" install --quiet -e "$REPO_ROOT[dev,mcp]"
    echo "  Done."
else
    echo ""
    echo "→ Skipping venv (--skip-venv)"
fi

# ── Step 2: rbc_security (optional) ──────────────────────────────────────────
echo ""
echo "→ Attempting rbc_security install (optional RBC SSL package) ..."
if "$PIP" install --quiet rbc_security 2>/dev/null; then
    echo "  rbc_security installed."
else
    echo "  Not available — skipping (expected outside RBC network)."
fi

# ── Step 3: pymupdf ───────────────────────────────────────────────────────────
echo ""
echo "→ Installing pymupdf (PDF vision support) ..."
if "$PIP" install --quiet pymupdf 2>/dev/null; then
    echo "  pymupdf installed."
else
    echo "  Warning: pymupdf install failed. PDF ingestion will not work."
fi

# ── Step 4: .env file ─────────────────────────────────────────────────────────
echo ""
if [ ! -f "$ENV_FILE" ]; then
    echo "→ Detecting Postgres configuration ..."

    # Auto-detect the DSN by scanning for local socket files
    DETECTED_DSN=$("$PYTHON" "$REPO_ROOT/scripts/setup_postgres.py" --print-dsn 2>/dev/null || echo "")

    if [ -n "$DETECTED_DSN" ]; then
        echo "  Detected DSN: $DETECTED_DSN"
    else
        DETECTED_DSN="postgresql://$(whoami)@localhost/docx_agent"
        echo "  Could not detect — using default: $DETECTED_DSN"
    fi

    echo "→ Creating .env from template ..."
    # Replace the example DSN with the detected one
    sed "s|^DOCX_AGENT_DATABASE_DSN=.*|DOCX_AGENT_DATABASE_DSN=$DETECTED_DSN|" \
        "$ENV_EXAMPLE" > "$ENV_FILE"

    echo ""
    echo "  ┌────────────────────────────────────────────────────────────────┐"
    echo "  │  .env created. One thing you must fill in:                     │"
    echo "  │                                                                 │"
    echo "  │  For direct OpenAI (home/dev):                                 │"
    echo "  │    OPENAI_API_KEY=sk-...                                        │"
    echo "  │                                                                 │"
    echo "  │  For RBC internal gateway (work):                              │"
    echo "  │    OPENAI_BASE_URL=https://...                                  │"
    echo "  │    OPENAI_OAUTH_TOKEN_URL=https://...                           │"
    echo "  │    OPENAI_OAUTH_CLIENT_ID=...                                   │"
    echo "  │    OPENAI_OAUTH_CLIENT_SECRET=...                               │"
    echo "  │    OPENAI_CHAT_MODEL=your-deployment-name                       │"
    echo "  │    OPENAI_EMBEDDING_MODEL=your-embedding-deployment             │"
    echo "  │    OPENAI_MAX_COMPLETION_TOKENS=32768                           │"
    echo "  └────────────────────────────────────────────────────────────────┘"
    echo ""
    echo "  Edit .env now, then re-run this script or run step 5 manually."
else
    echo "→ .env already exists — loading it for Postgres setup."
fi

# ── Step 5: Postgres setup ────────────────────────────────────────────────────
if [ "$SKIP_DB" = false ]; then
    echo ""
    echo "→ Setting up Postgres database ..."

    # Load .env so DOCX_AGENT_DATABASE_DSN is available
    if [ -f "$ENV_FILE" ]; then
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE"
        set +a
    fi

    if "$PYTHON" "$REPO_ROOT/scripts/setup_postgres.py" 2>&1 | grep -v "^DSN="; then
        echo "  Postgres setup complete."
    else
        echo ""
        echo "  Warning: Postgres setup encountered issues."
        echo "  Check that Postgres is running, then retry:"
        echo "    python scripts/setup_postgres.py"
    fi
else
    echo ""
    echo "→ Skipping Postgres (--skip-db). Run later with:"
    echo "    source .env && python scripts/setup_postgres.py"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Setup complete!"
echo "════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo ""
echo "  1. Activate the virtual environment:"
echo "       source .venv/bin/activate"
echo ""
echo "  2. Check / fill in your API credentials in .env:"
echo "       \$EDITOR .env"
echo ""
echo "  3. Ingest all data files:"
echo "       source .env && python -m data_sources.scripts.ingest_batch --ensure-schema"
echo ""
echo "  4. Run the stress test (first 5 queries to verify):"
echo "       source .env && python -m data_sources.scripts.stress_test --max-queries 5"
echo ""
echo "  5. Open the HTML report:"
echo "       open data/stress_test_reports/stress_test_report.html"
echo ""
