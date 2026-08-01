#!/usr/bin/env bash
# ============================================================================
# install_mt5.sh — Phase 9a VPS deployment (Linux / Wine)
#
# Creates a portable, multi-instance MT5 directory structure and copies the
# Edgelab MT5 config placeholders. This is infrastructure only; it does NOT
# install the MetaTrader5 Python package (that is Phase 9b).
#
# Run on the VPS as the trading user. Idempotent, but WILL overwrite the
# placeholder config files if they already exist (they are placeholders only).
# ============================================================================
set -euo pipefail

MT5_ROOT="${MT5_ROOT:-$HOME/mt5}"
EDITIONS=("MT5_Instance1" "MT5_Instance2")
INSTANCES="${MT5_INSTANCES:-${EDITIONS[*]}}"

echo "[install_mt5] MT5 root: $MT5_ROOT"

mkdir -p "$MT5_ROOT"

# ---- portable mode marker (lets MT5 store data next to the binary) ----
if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* || "$OSTYPE" == "win32"* ]]; then
    # Windows / Git-Bash
    for d in $INSTANCES; do
        inst="$MT5_ROOT/$d"
        mkdir -p "$inst"
        : > "$inst/portable"
    done
else
    # Linux / Wine
    for d in $INSTANCES; do
        inst="$MT5_ROOT/$d"
        mkdir -p "$inst"
        touch "$inst/portable"
    done
fi

# ---- MQL5 sub-directory structure ----
for d in $INSTANCES; do
    inst="$MT5_ROOT/$d"
    mkdir -p "$inst/MQL5/Experts"
    mkdir -p "$inst/MQL5/Presets"
    mkdir -p "$inst/MQL5/Files"
    mkdir -p "$inst/MQL5/Include"
    mkdir -p "$inst/MQL5/Indicators"
    mkdir -p "$inst/MQL5/Scripts"

    # ---- placeholder config files (operator fills real values) ----
    if [[ ! -f "$inst/accounts.xml" ]]; then
        cat > "$inst/accounts.xml" <<'XML'
<!-- Edgelab MT5 account placeholder. Replace with real broker account.xml -->
<accounts>
  <account server="CHANGE-ME" login="00000000" password="CHANGE-ME" />
</accounts>
XML
    fi
    if [[ ! -f "$inst/terminal64.ini" ]]; then
        cat > "$inst/terminal64.ini" <<'INI'
; Edgelab MT5 terminal64.ini placeholder
[Common]
Login=00000000
Server=CHANGE-ME
INI
    fi

    # ---- permissions (Linux only) ----
    if [[ "$OSTYPE" != "msys"* && "$OSTYPE" != "cygwin"* && "$OSTYPE" != "win32"* ]]; then
        chmod 755 "$inst" 2>/dev/null || true
        chmod 644 "$inst/accounts.xml" "$inst/terminal64.ini" 2>/dev/null || true
    fi
done

echo "[install_mt5] done. Instances created: $INSTANCES"
echo "[install_mt5] Next: edit accounts.xml / terminal64.ini in each instance, then deploy the EA."
