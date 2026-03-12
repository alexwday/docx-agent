#!/usr/bin/env bash
# serve.sh — Start the docx-agent UI server and open it in the browser.
#
# Usage:
#   ./scripts/serve.sh              # Start fresh
#   ./scripts/serve.sh --restart    # Kill existing servers, then start fresh
#   ./scripts/serve.sh --stop       # Just kill existing servers
#
# Environment variables (optional):
#   PORT             — UI server port (default: 8030)
#   HOST             — UI server bind address (default: 127.0.0.1)
#   ALLOWED_ROOT     — Document root directory (default: project root)
#   OPENAI_MODEL     — Model for agent features (default: gpt-4.1)
#   NO_OPEN          — Set to 1 to skip opening the browser

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Activate virtual environment
VENV_DIR="$PROJECT_DIR/.venv"
if [[ -f "$VENV_DIR/bin/activate" ]]; then
    source "$VENV_DIR/bin/activate"
elif [[ -f "$PROJECT_DIR/venv/bin/activate" ]]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

# Defaults
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8030}"
ALLOWED_ROOT="${ALLOWED_ROOT:-$PROJECT_DIR}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4.1}"
NO_OPEN="${NO_OPEN:-0}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[serve]${NC} $*"; }
warn() { echo -e "${YELLOW}[serve]${NC} $*"; }
err()  { echo -e "${RED}[serve]${NC} $*" >&2; }

kill_existing() {
    local pids
    pids=$(pgrep -f 'word-ui-server|word_ui\.web_server' 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        warn "Stopping existing UI server (PIDs: $pids)..."
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
        # Force kill any stragglers
        pids=$(pgrep -f 'word-ui-server|word_ui\.web_server' 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            echo "$pids" | xargs kill -9 2>/dev/null || true
        fi
        log "Stopped."
    else
        log "No existing servers found."
    fi
}

# Parse arguments
ACTION="start"
for arg in "$@"; do
    case "$arg" in
        --restart) ACTION="restart" ;;
        --stop)    ACTION="stop" ;;
        --no-open) NO_OPEN=1 ;;
        --help|-h)
            echo "Usage: $0 [--restart|--stop|--no-open]"
            echo ""
            echo "Options:"
            echo "  --restart   Kill existing servers, then start"
            echo "  --stop      Kill existing servers and exit"
            echo "  --no-open   Don't open browser automatically"
            echo ""
            echo "Environment:"
            echo "  PORT=$PORT  HOST=$HOST  ALLOWED_ROOT=$ALLOWED_ROOT"
            exit 0
            ;;
        *)
            err "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

# Execute
if [[ "$ACTION" == "stop" ]]; then
    kill_existing
    exit 0
fi

if [[ "$ACTION" == "restart" ]]; then
    kill_existing
fi

# Check if port is already in use
if lsof -i ":$PORT" -sTCP:LISTEN &>/dev/null; then
    err "Port $PORT is already in use."
    err "Run '$0 --restart' to kill existing servers first."
    exit 1
fi

# Build the command
CMD=(
    word-ui-server
    --host "$HOST"
    --port "$PORT"
    --allowed-root "$ALLOWED_ROOT"
    --openai-model "$OPENAI_MODEL"
)

# Add database DSN if available
if [[ -n "${DOCX_AGENT_DATABASE_DSN:-}" ]] || [[ -n "${DATABASE_URL:-}" ]]; then
    log "Postgres DSN detected — V2 API will be enabled."
fi

log "Starting UI server..."
echo -e "  ${CYAN}URL:${NC}          http://$HOST:$PORT"
echo -e "  ${CYAN}Allowed root:${NC} $ALLOWED_ROOT"
echo -e "  ${CYAN}Model:${NC}        $OPENAI_MODEL"
echo ""

# Start server in background
"${CMD[@]}" &
SERVER_PID=$!

# Give the server a moment to start
sleep 2

# Check it actually started
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    err "Server failed to start. Check the output above for errors."
    exit 1
fi

log "Server running (PID: $SERVER_PID)"

# Open browser
if [[ "$NO_OPEN" != "1" ]]; then
    URL="http://$HOST:$PORT"
    if command -v open &>/dev/null; then
        open "$URL"
        log "Opened $URL in browser."
    elif command -v xdg-open &>/dev/null; then
        xdg-open "$URL"
        log "Opened $URL in browser."
    else
        warn "Could not detect browser opener. Navigate to: $URL"
    fi
fi

echo ""
log "Press Ctrl+C to stop the server."
echo ""

# Wait for the server process (allows Ctrl+C to propagate)
wait "$SERVER_PID"
