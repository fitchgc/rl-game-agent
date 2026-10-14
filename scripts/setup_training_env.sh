#!/usr/bin/env bash
# One-shot environment setup for the ruggrogue PPO training machine (GPU).
# Idempotent: safe to re-run. Run from the repo root.
#
#   bash scripts/setup_training_env.sh
#
# Env overrides:
#   TORCH_INDEX_URL  PyTorch CUDA wheel index (default cu126).
#                    Pick your CUDA build at https://pytorch.org/get-started/locally/
#   GAME_BASE_URL    Where to fetch the game files (default: official site).
#   SKIP_TORCH       Set to 1 to skip torch install (you manage torch yourself).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu126}"
GAME_BASE_URL="${GAME_BASE_URL:-https://tung.github.io/ruggrogue/play}"
MANIFEST="scripts/ruggrogue-manifest.json"
WEB_DIR="vendor/ruggrogue-web"

echo "==> repo: $REPO_ROOT"

# 1. Python version -----------------------------------------------------------
PY="$(command -v python3)"
PY_VER="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "==> python: $("$PY" --version 2>&1) at $PY"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "need python >= 3.10"'

# 2. venv ---------------------------------------------------------------------
if [ ! -d .venv ]; then
  echo "==> creating .venv"
  "$PY" -m venv .venv
else
  echo "==> .venv exists, reusing"
fi
VPY=".venv/bin/python"
"$VPY" -m pip install -q --upgrade pip

# 3. torch (CUDA) -------------------------------------------------------------
if [ "${SKIP_TORCH:-0}" != "1" ]; then
  echo "==> installing torch from $TORCH_INDEX_URL"
  "$VPY" -m pip install -q torch --index-url "$TORCH_INDEX_URL"
fi
"$VPY" -c "import torch; print('torch', torch.__version__, '| cuda:', torch.cuda.is_available())"

# 4. project deps -------------------------------------------------------------
echo "==> installing project deps"
"$VPY" -m pip install -q -e .

# 5. playwright chromium -------------------------------------------------------
echo "==> installing playwright chromium"
"$VPY" -m playwright install chromium 2>&1 | tail -2 || true
echo "    (if browser launch fails on missing system libs, run: sudo .venv/bin/playwright install-deps chromium)"

# 6. game files ---------------------------------------------------------------
echo "==> fetching game files into $WEB_DIR"
mkdir -p "$WEB_DIR"
"$VPY" - <<EOF
import hashlib, json, urllib.request
from pathlib import Path

manifest = json.loads(Path("$MANIFEST").read_text())
web = Path("$WEB_DIR")
ok = True
for entry in manifest["required_files"]:
    rel, want = entry["path"], entry["sha256"]
    dest = web / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == want:
        print(f"  cached  {rel}")
        continue
    url = "$GAME_BASE_URL/" + rel
    print(f"  fetch   {rel}")
    urllib.request.urlretrieve(url, dest)
    got = hashlib.sha256(dest.read_bytes()).hexdigest()
    if got != want:
        print(f"  MISMATCH {rel}: got {got[:16]} want {want[:16]}")
        ok = False
if not ok:
    raise SystemExit("checksum mismatch -- refusing to continue")
# write the manifest the env's B1 gate expects
(web / "MANIFEST.json").write_text(Path("$MANIFEST").read_text())
print("  game files verified against manifest")
EOF

# 7. static server ------------------------------------------------------------
if curl -sf -o /dev/null http://localhost:8901/index.html; then
  echo "==> game server already up on :8901"
else
  echo "==> starting game server on :8901"
  nohup "$PY" -m http.server 8901 --directory "$WEB_DIR" >/tmp/ruggrogue-server.log 2>&1 &
  for _ in $(seq 1 20); do
    sleep 0.5
    curl -sf -o /dev/null http://localhost:8901/index.html && break
  done
  curl -sf -o /dev/null http://localhost:8901/index.html \
    && echo "==> game server up" \
    || { echo "server failed to start; see /tmp/ruggrogue-server.log"; exit 1; }
fi

echo
echo "==> setup complete. Smoke-check the env:"
echo "    .venv/bin/python -c \"from rl_game_agent.envs import ENV_REGISTRY; e=ENV_REGISTRY['ruggrogue-v1'](); print(e.reset()[0].shape); e.close()\""
echo "    then see docs/gpu-training.md for the training commands."
