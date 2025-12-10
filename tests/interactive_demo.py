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
Interactive demo: starts a viewer, opens the browser, and sends plots.

Usage:
    uv run tests/interactive_demo.py
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.getcwd(), ".mplconfig"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# High-DPI settings for crisp plots
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["font.size"] = 11

from rileyviewer import Viewer


def main() -> None:
    print("Starting viewer...")
    # Uses default port 7878 and auto-opens browser on first plot
    viewer = Viewer()

    url = f"http://{viewer.addr}"
    if viewer.token:
        url += f"?token={viewer.token}"

    print(f"Viewer running at: {url}")
    print("Browser will open on first plot...")

    print("\nSending plots (Ctrl+C to stop)...\n")

    try:
        # Plot 1: Simple line
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot([0, 1, 2, 3, 4], [0, 1, 4, 9, 16], "b-o", linewidth=2)
        ax.set_title("Plot 1: Quadratic")
        ax.set_xlabel("x")
        ax.set_ylabel("y = x²")
        ax.grid(True, alpha=0.3)
        plot_id = viewer.show(fig)
        plt.close(fig)
        print(f"Sent plot 1: {plot_id}")
        time.sleep(2)

        # Plot 2: Sine wave
        fig, ax = plt.subplots(figsize=(10, 6))
        x = np.linspace(0, 4 * np.pi, 200)
        ax.plot(x, np.sin(x), "r-", linewidth=2, label="sin(x)")
        ax.plot(x, np.cos(x), "g--", linewidth=2, label="cos(x)")
        ax.set_title("Plot 2: Trigonometry")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plot_id = viewer.show(fig)
        plt.close(fig)
        print(f"Sent plot 2: {plot_id}")
        time.sleep(2)

        # Plot 3: Scatter plot
        fig, ax = plt.subplots(figsize=(10, 6))
        np.random.seed(42)
        x = np.random.randn(100)
        y = x + np.random.randn(100) * 0.5
        colors = np.random.rand(100)
        ax.scatter(x, y, c=colors, cmap="viridis", alpha=0.7, s=50)
        ax.set_title("Plot 3: Scatter")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        plot_id = viewer.show(fig)
        plt.close(fig)
        print(f"Sent plot 3: {plot_id}")
        time.sleep(2)

        # Plot 4: Bar chart
        fig, ax = plt.subplots(figsize=(10, 6))
        categories = ["A", "B", "C", "D", "E"]
        values = [23, 45, 56, 78, 32]
        bars = ax.bar(categories, values, color=plt.cm.Paired.colors[:5])
        ax.set_title("Plot 4: Bar Chart")
        ax.set_ylabel("Value")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                   str(val), ha="center", va="bottom")
        plot_id = viewer.show(fig)
        plt.close(fig)
        print(f"Sent plot 4: {plot_id}")
        time.sleep(2)

        # Plot 5: Heatmap
        fig, ax = plt.subplots(figsize=(10, 7))
        data = np.random.rand(8, 8)
        im = ax.imshow(data, cmap="coolwarm")
        ax.set_title("Plot 5: Heatmap")
        fig.colorbar(im, ax=ax)
        plot_id = viewer.show(fig)
        plt.close(fig)
        print(f"Sent plot 5: {plot_id}")

        print("\n--- All plots sent! ---")
        print("Press Ctrl+C to shutdown the viewer...")

        # Keep running so the viewer stays up
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        viewer.shutdown()
        print("Done!")


if __name__ == "__main__":
    main()
