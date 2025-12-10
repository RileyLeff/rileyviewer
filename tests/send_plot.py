#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "matplotlib",
#   "numpy",
#   "rileyviewer @ file:///${PROJECT_ROOT}/python",
# ]
# ///
"""
Simple script to send a single plot to the viewer.
Run this multiple times to see plots accumulate in the same browser window.

Usage:
    uv run tests/send_plot.py

The first run starts the server (as a background process) and opens the browser.
Subsequent runs connect to the same server and send plots.

To stop the server:
    ./target/debug/rileyviewer stop
"""

import os
import random

os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.getcwd(), ".mplconfig"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 150

from rileyviewer import Viewer


def main():
    # Server runs as a detached background process
    # First run spawns it, subsequent runs connect to it
    viewer = Viewer()

    print(f"Connected to: {viewer.addr}")

    # Generate a random plot
    plot_type = random.choice(["line", "scatter", "bar", "hist"])

    fig, ax = plt.subplots(figsize=(8, 5))

    if plot_type == "line":
        x = np.linspace(0, 4 * np.pi, 100)
        phase = random.uniform(0, 2 * np.pi)
        ax.plot(x, np.sin(x + phase), linewidth=2)
        ax.set_title(f"Sine wave (phase={phase:.2f})")

    elif plot_type == "scatter":
        n = random.randint(50, 200)
        x = np.random.randn(n)
        y = x * random.uniform(0.5, 2) + np.random.randn(n) * 0.5
        ax.scatter(x, y, alpha=0.6, c=np.random.rand(n), cmap="viridis")
        ax.set_title(f"Scatter ({n} points)")

    elif plot_type == "bar":
        categories = list("ABCDEFGH")[:random.randint(4, 8)]
        values = [random.randint(10, 100) for _ in categories]
        ax.bar(categories, values, color=plt.cm.Set2.colors[:len(categories)])
        ax.set_title("Random bar chart")

    else:  # hist
        data = np.random.randn(500) * random.uniform(1, 3) + random.uniform(-2, 2)
        ax.hist(data, bins=30, alpha=0.7, edgecolor="black")
        ax.set_title("Random histogram")

    ax.grid(True, alpha=0.3)

    plot_id = viewer.show(fig)
    print(f"Sent {plot_type} plot: {plot_id[:8]}...")
    print("\nRun this script again to send more plots!")
    print("Use 'cargo run --package rv_cli -- stop' to stop the server.")


if __name__ == "__main__":
    main()
