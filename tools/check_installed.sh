#!/usr/bin/env bash
# Run against an installed wheel, outside the source checkout.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
wheel=$(realpath "${1:?usage: check_installed.sh WHEEL}")
work=$(mktemp -d "${TMPDIR:-/tmp}/panelframe-installed.XXXXXXXX")
cleanup() { chmod -R u+w "$work/tests" 2>/dev/null || true; rm -rf "$work"; }
trap cleanup EXIT
python -m venv "$work/venv"
"$work/venv/bin/python" -m pip install --disable-pip-version-check --no-index --no-deps "$wheel"
cp -R "$root/tests" "$work/tests"
find "$work/tests" -type d -name __pycache__ -prune -exec rm -rf {} +
chmod -R a-w "$work/tests"
cd "$work"
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1
"$work/venv/bin/python" - <<'PY'
from pathlib import Path
import panelframe
p=Path(panelframe.__file__).resolve()
assert 'site-packages' in p.parts, p
print('Installed module:', p)
PY
"$work/venv/bin/python" -m unittest discover -s tests -t . -v
"$work/venv/bin/panelframe" --version
