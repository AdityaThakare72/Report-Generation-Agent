#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# setup.sh — Bootstrap the project environment
# Usage:  chmod +x setup.sh && ./setup.sh
# ──────────────────────────────────────────────────────────────
set -euo pipefail

VENV_DIR="venv"
PYTHON="python3"

echo "═══════════════════════════════════════════════════════"
echo "  AI Compliance Monitoring Agent — Environment Setup"
echo "═══════════════════════════════════════════════════════"

# ── 1. Create virtual environment ────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/4] Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
else
    echo "[1/4] Virtual environment already exists. Skipping."
fi

# ── 2. Activate the virtual environment ──────────────────────
echo "[2/4] Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# ── 3. Upgrade pip ───────────────────────────────────────────
echo "[3/4] Upgrading pip..."
pip install --upgrade pip --quiet

# ── 4. Install dependencies ─────────────────────────────────
echo "[4/4] Installing dependencies from requirements.txt..."
pip install -r requirements.txt --quiet

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅  Setup complete!"
echo ""
echo "  Activate the environment with:"
echo "    source venv/bin/activate"
echo ""
echo "  Then copy .env.example to .env and add your API key:"
echo "    cp .env.example .env"
echo "═══════════════════════════════════════════════════════"
