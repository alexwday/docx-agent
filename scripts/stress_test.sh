#!/usr/bin/env bash
# stress_test.sh — Run the multi-source retrieval stress test.
#
# Usage:
#   ./scripts/stress_test.sh                  # All 60 queries
#   ./scripts/stress_test.sh --pillar3        # Pillar 3 queries only (20)
#   ./scripts/stress_test.sh --pillar3 -n 5   # First 5 pillar3 queries
#   ./scripts/stress_test.sh --supp           # Supplementary financials only
#   ./scripts/stress_test.sh --slides         # Investor slides only
#
# Environment variables (required):
#   DOCX_AGENT_DATABASE_DSN   — Postgres DSN  (e.g. postgresql://user:pass@host:5432/db)
#   OPENAI_API_KEY            — OpenAI API key
#
# Environment variables (optional):
#   STRESS_OUTPUT_DIR         — Report output directory (default: data/stress_test_reports)
#   STRESS_PARALLEL           — Concurrent queries (default: 4)

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

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[stress-test]${NC} $*"; }
warn() { echo -e "${YELLOW}[stress-test]${NC} $*"; }
err()  { echo -e "${RED}[stress-test]${NC} $*" >&2; }

# Defaults
OUTPUT_DIR="${STRESS_OUTPUT_DIR:-$PROJECT_DIR/data/stress_test_reports}"
PARALLEL="${STRESS_PARALLEL:-4}"
SOURCE_FILTER=""
MAX_QUERIES=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pillar3)    SOURCE_FILTER="pillar3" ;;
        --supp)       SOURCE_FILTER="supp_financials" ;;
        --slides)     SOURCE_FILTER="investor_slides" ;;
        -n|--max)
            shift
            MAX_QUERIES="$1"
            ;;
        -p|--parallel)
            shift
            PARALLEL="$1"
            ;;
        -o|--output)
            shift
            OUTPUT_DIR="$1"
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Source filter (pick one):"
            echo "  --pillar3         Run pillar3 queries only"
            echo "  --supp            Run supp_financials queries only"
            echo "  --slides          Run investor_slides queries only"
            echo "  (none)            Run all 60 queries"
            echo ""
            echo "Options:"
            echo "  -n, --max N       Run only the first N matching queries"
            echo "  -p, --parallel N  Concurrent queries (default: $PARALLEL)"
            echo "  -o, --output DIR  Report output directory (default: data/stress_test_reports)"
            echo ""
            echo "Required env:"
            echo "  DOCX_AGENT_DATABASE_DSN   Postgres connection string"
            echo "  OPENAI_API_KEY            OpenAI API key"
            echo ""
            echo "Optional env:"
            echo "  STRESS_OUTPUT_DIR         Override default output directory"
            echo "  STRESS_PARALLEL           Override default parallelism"
            exit 0
            ;;
        *)
            err "Unknown argument: $1"
            err "Run '$0 --help' for usage."
            exit 1
            ;;
    esac
    shift
done

# Validate required env vars
MISSING=()
[[ -z "${DOCX_AGENT_DATABASE_DSN:-}${DATABASE_URL:-}" ]] && MISSING+=("DOCX_AGENT_DATABASE_DSN")
[[ -z "${OPENAI_API_KEY:-}" ]] && MISSING+=("OPENAI_API_KEY")
if [[ ${#MISSING[@]} -gt 0 ]]; then
    err "Missing required environment variables: ${MISSING[*]}"
    err "Export them before running, e.g.:"
    err "  export DOCX_AGENT_DATABASE_DSN='postgresql://user:pass@host:5432/db'"
    err "  export OPENAI_API_KEY='sk-...'"
    exit 1
fi

# Build the command
CMD=(
    python -m data_sources.scripts.stress_test
    --output-dir "$OUTPUT_DIR"
    --parallel-queries "$PARALLEL"
)
[[ -n "$SOURCE_FILTER" ]] && CMD+=(--source-filter "$SOURCE_FILTER")
[[ -n "$MAX_QUERIES" ]]   && CMD+=(--max-queries "$MAX_QUERIES")

# Print config
log "Starting stress test..."
echo -e "  ${CYAN}Filter:${NC}    ${SOURCE_FILTER:-all queries}"
echo -e "  ${CYAN}Max:${NC}       ${MAX_QUERIES:-unlimited}"
echo -e "  ${CYAN}Parallel:${NC}  $PARALLEL"
echo -e "  ${CYAN}Output:${NC}    $OUTPUT_DIR"
echo ""

cd "$PROJECT_DIR"
"${CMD[@]}"
