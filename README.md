# rileyviewer

A browser-based plot viewer for Python. Send plots from your script, see them instantly in a persistent browser tab.

Inspired by [httpgd](https://nx10.github.io/httpgd/) for R. Built because `plt.show()` blocks your program, IDEs render plots in tiny panels, and LLMs leave `.png` files all over your project.

## Install

**Server** (install once):

```bash
# macOS
brew install rileyleff/tap/rileyviewer

# or from source
cargo install rileyviewer

# or grab a binary from GitHub Releases
# https://github.com/rileyleff/rileyviewer/releases
```

**Python client:**

```
uv add rileyviewer
```

Requires Python 3.10+. The Python package is a pure HTTP client — it connects to the server but doesn't bundle it.

## Quick start

Start the server in a terminal:

```bash
rileyviewer serve
```

This opens a browser tab that stays open across script runs. Then send plots from Python:

```python
from rileyviewer import Viewer
import matplotlib.pyplot as plt

v = Viewer()  # connects to running server

with v.capture() as ctx:
    plt.plot([1, 2, 3], [1, 4, 9])
    plt.title("My Plot")
    ctx.push()  # sends current figure to browser

    plt.figure()
    plt.scatter([1, 2, 3], [3, 2, 1])
    ctx.push()  # sends this one too
# figures closed automatically
```

If the server isn't running, `Viewer()` raises a helpful error with install instructions.

## Supported frameworks

`v.show(obj)` auto-detects the plot type:

| Framework | How it works |
|-----------|-------------|
| **matplotlib** | Renders via `savefig` (SVG or PNG) |
| **seaborn** | Extracts underlying matplotlib figure |
| **pandas** | `.plot()` returns matplotlib axes |
| **Plotly** | Serializes to Plotly JSON |
| **Altair** | Serializes to Vega-Lite JSON |
| **matplotlib animations** | Converts to interactive HTML via `to_jshtml()` |
| **Anything with `_repr_html_()`** | Sends as HTML iframe |

You can also send raw content directly:

```python
v.send_svg(svg_string)
v.send_png_bytes(png_bytes)
v.send_plotly_json(json_string)
v.send_vega_json(json_string)      # Vega or Vega-Lite
v.send_html(html_string)
```

## How it works

```
Python  ──HTTP POST──>  Rust server  ──WebSocket──>  Browser (Svelte SPA)
```

The server runs as a standalone process. It serves a single-page app and pushes plots to connected browsers via WebSocket. The Python client sends plots via HTTP — no WebSocket or subprocess management needed.

The browser tab persists across script runs. Plots accumulate in a thumbnail strip — click any to view it.

## Multiple clients

Multiple Python processes can send to the same server:

```python
# Both connect to the same running server
v1 = Viewer(port=9877)
v2 = Viewer(port=9877)
```

The server stores a token in `~/Library/Application Support/rileyviewer/server.json` (macOS) so clients authenticate automatically.

## Configuration

```python
Viewer(
    port=7878,              # default port
    host="127.0.0.1",      # server address
    default_format="svg",   # "svg" or "png" for matplotlib
)
```

The browser UI has a settings menu for theme (light/dark/auto), background style, and thumbnail position.

## Architecture

- **`crates/`** — Rust server (Axum) and CLI, installed standalone
- **`python/`** — Pure Python HTTP client (`uv add rileyviewer`)
- **`web/`** — SvelteKit frontend with Tailwind, builds to static assets embedded in the server binary

## Development

```bash
# Build web assets
cd web && npm ci && npm run build && cd ..

# Run server in dev mode (serves from web/dist/)
cargo run --release -- serve --port 9877

# Python client (editable install)
cd python && uv sync && cd ..
```

## License

MIT
