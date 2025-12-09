## rileyviewer (Python)

Thin Python wrapper around the Rust backend for RileyViewer. The Rust extension is built with `maturin` and exposed as `rileyviewer._core`, while `rileyviewer.viewer.Viewer` provides a friendly API and adapters.

### Dev quickstart

```bash
# one-time: create a venv at repo root so maturin can find it
uv venv
# activate shell env (zsh/bash)
source .venv/bin/activate

# one-time: install maturin
uv pip install maturin

# build web assets if you want embedded UI
./scripts/build-web.sh

# build/install the extension in editable mode (run from repo root or python/)
uv run --project python maturin develop

uv run python - <<'PY'
from rileyviewer import Viewer
v = Viewer()
print("Server at", v.addr, "token", v.token)
v.shutdown()
PY

# integration smoke (after `maturin develop`)
uv run tests/send_plot_smoke.py
```
