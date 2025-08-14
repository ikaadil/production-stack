#!/usr/bin/env bash
#
# Minimal Router Stress Test (ab or wrk)
# - Targets an already-running router at localhost:9080 (configurable).
# - Fires JSON POSTs to /v1/chat/completions.
# - No auth headers.
#
# Examples:
#   ./stress-test.sh
#   ./stress-test.sh -c 1000 -n 20000 -p 9080 -m meta-llama/Llama-3.1-8B-Instruct
#   ./stress-test.sh --wrk

set -euo pipefail

# ---------- Defaults ----------
PORT=9080
CONCURRENT=2000
REQUESTS=20000
MODEL="meta-llama/Llama-3.1-8B-Instruct"
MAX_TOKENS=16
PROMPT="What is the capital of France?"
USE_WRK=false
PAYLOAD_FILE="$(mktemp -t vllm-stress.XXXXXX.json)"
HEADER_TYPE="Content-Type: application/json"

# ---------- Colors ----------
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info(){ echo -e "${GREEN}[INFO]${NC} $*"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $*"; }
err(){  echo -e "${RED}[ERROR]${NC} $*"; }

# ---------- Help ----------
usage(){
  cat <<EOF
Minimal Router Stress Test (no auth)

Usage: $0 [options]

Options:
  -c, --concurrent N     Concurrent requests (default: ${CONCURRENT})
  -n, --requests N       Total requests (default: ${REQUESTS})
  -p, --port PORT        Router port (default: ${PORT})
  -m, --model NAME       Model name (default: ${MODEL})
  -t, --max-tokens N     max_tokens for generation (default: ${MAX_TOKENS})
  --prompt TEXT          User prompt text (default: "${PROMPT}")
  --wrk                  Prefer wrk (if installed) instead of ab
  -h, --help             Show this help

Endpoint:
  http://localhost:PORT/v1/chat/completions
EOF
}

# ---------- Argparse ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--concurrent) CONCURRENT="$2"; shift 2;;
    -n|--requests)   REQUESTS="$2";   shift 2;;
    -p|--port)       PORT="$2";       shift 2;;
    -m|--model)      MODEL="$2";      shift 2;;
    -t|--max-tokens) MAX_TOKENS="$2"; shift 2;;
    --prompt)        PROMPT="$2";     shift 2;;
    --wrk)           USE_WRK=true;    shift 1;;
    -h|--help)       usage; exit 0;;
    *) err "Unknown option: $1"; usage; exit 1;;
  esac
done

ENDPOINT="http://localhost:${PORT}/v1/chat/completions"

# ---------- Preflight ----------
have_cmd(){ command -v "$1" >/dev/null 2>&1; }

if ! curl -sSf -o /dev/null "${ENDPOINT%/}/" 2>/dev/null; then
  warn "Endpoint probe failed (expected if GET isn't supported). Continuing…"
fi

AB_OK=false; WRK_OK=false
if have_cmd ab;  then AB_OK=true; fi
if have_cmd wrk; then WRK_OK=true; fi
if [[ "${USE_WRK}" != true && "${AB_OK}" != true && "${WRK_OK}" != true ]]; then
  err "Neither 'ab' nor 'wrk' found. Install one (e.g., 'sudo apt-get install apache2-utils' or 'brew install wrk')."
  exit 1
fi
if [[ "${USE_WRK}" == true && "${WRK_OK}" != true ]]; then
  err "wrk requested but not found."
  exit 1
fi

# ---------- Build payload ----------
cat > "${PAYLOAD_FILE}" <<EOF
{
  "model": "${MODEL}",
  "messages": [{"role": "user", "content": "${PROMPT}"}],
  "max_tokens": ${MAX_TOKENS}
}
EOF
trap 'rm -f "${PAYLOAD_FILE}"' EXIT

info "Stress test config:"
info "  Endpoint:     ${ENDPOINT}"
info "  Model:        ${MODEL}"
info "  Concurrency:  ${CONCURRENT}"
info "  Total reqs:   ${REQUESTS}"
info "  max_tokens:   ${MAX_TOKENS}"
info "  Tool:         \$([[ ${USE_WRK} == true ]] && echo wrk || ( [[ ${AB_OK} == true ]] && echo ab || echo wrk ))"

# ---------- Warmup (one request) ----------
info "Warming up (1 request via curl)…"
set +e
WARMUP_RES=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${ENDPOINT}" \
  -H "${HEADER_TYPE}" --data @"${PAYLOAD_FILE}")
set -e
if [[ "${WARMUP_RES}" != "200" ]]; then
  warn "Warmup returned HTTP ${WARMUP_RES}. Continuing with load anyway…"
fi

# ---------- Run test ----------
if [[ "${USE_WRK}" == true || "${AB_OK}" != true ]]; then
  if [[ "${WRK_OK}" != true ]]; then
    err "wrk not installed."
    exit 1
  fi

  LUA_SCRIPT="$(mktemp -t vllm-wrk.XXXXXX.lua)"
  trap 'rm -f "${PAYLOAD_FILE}" "${LUA_SCRIPT}"' EXIT
  cat > "${LUA_SCRIPT}" <<'LUA'
wrk.method = "POST"
local file = io.open(os.getenv("PAYLOAD_FILE"), "r")
local body = file:read("*a")
file:close()
wrk.body = body
wrk.headers["Content-Type"] = "application/json"
LUA

  DURATION="30s"
  info "Running wrk for ${DURATION} at ~${CONCURRENT} connections…"
  wrk -t "$(min_threads=${CONCURRENT}; [[ ${min_threads} -gt 16 ]] && echo 16 || echo ${min_threads})" \
      -c "${CONCURRENT}" \
      -d "${DURATION}" \
      -s "${LUA_SCRIPT}" \
      "${ENDPOINT}"
else
  info "Running ab: -c ${CONCURRENT} -n ${REQUESTS}"
  ab -c "${CONCURRENT}" \
     -n "${REQUESTS}" \
     -p "${PAYLOAD_FILE}" \
     -T "application/json" \
     "${ENDPOINT}"
fi

info "Done."
