# rileyviewer

A browser-based plot viewer for Python. Send plots from your script, see them instantly in a persistent browser tab.

Inspired by [httpgd](https://nx10.github.io/httpgd/) for R. Built because `plt.show()` blocks your program, IDEs render plots in tiny panels, and LLMs leave `.png` files all over your project.

## Install

```
uv add rileyviewer
```

This installs both the Python library and the server binary. Requires Python 3.10+.

## Quick start

Start the server in a terminal:

```bash
rileyviewer serve
```

This opens a browser tab that stays open across script runs. Then send plots from Python:

```python
from rileyviewer import Viewer
import matplotlib.pyplot as plt

v = Viewer(open_browser=False)  # connects to running server

with v.capture() as ctx:
    plt.plot([1, 2, 3], [1, 4, 9])
    plt.title("My Plot")
    ctx.push()  # sends current figure to browser

    plt.figure()
    plt.scatter([1, 2, 3], [3, 2, 1])
    ctx.push()  # sends this one too
# figures closed automatically
```

You can also do everything from Python — `Viewer()` will start the server and open the browser for you if one isn't already running:

```python
v = Viewer()  # starts server + opens browser
v.show(plt.gcf())
```

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

The first `Viewer()` call spawns a local Rust server as a background process. The server serves a single-page app and pushes plots to connected browsers via WebSocket. Subsequent `Viewer()` calls on the same port reuse the existing server.

The browser tab persists across script runs. Plots accumulate in a thumbnail strip — click any to view it.

## Multiple clients

Multiple Python processes can send to the same server:

```python
# Process 1 — starts the server
v = Viewer(port=9877)

# Process 2 — connects to existing server
v = Viewer(port=9877, open_browser=False)
```

The server stores a token in `~/Library/Application Support/rileyviewer/server.json` (macOS) so subsequent clients authenticate automatically.

## Configuration

```python
Viewer(
    port=7878,              # default port
    host="127.0.0.1",      # bind address
    open_browser=True,      # open browser on first run
    default_format="svg",   # "svg" or "png" for matplotlib
    history_limit=200,      # max plots kept server-side
)
```

The browser UI has a settings menu for theme (light/dark/auto), background style, and thumbnail position.

## Architecture

- **`python/`** — Python package (`uv add rileyviewer`)
- **`crates/`** — Rust server (Axum), CLI, core types
- **`web/`** — SvelteKit frontend with Tailwind, builds to static assets embedded in the binary

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
