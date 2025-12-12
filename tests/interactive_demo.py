"""
Interactive demo: starts a viewer, opens the browser, and sends plots.

Demonstrates:
- SVG output (default) - crisp, scalable vector graphics
- PNG output - explicit raster format
- Matplotlib animations - interactive playback in browser

Usage:
    cd python && uv run python ../tests/interactive_demo.py
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.getcwd(), ".mplconfig"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

# High-DPI settings for crisp plots
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["font.size"] = 11

from rileyviewer import Viewer


def main() -> None:
    print("Starting viewer...")
    # SVG is now the default format for matplotlib figures
    viewer = Viewer()

    url = f"http://{viewer.addr}"
    if viewer.token:
        url += f"?token={viewer.token}"

    print(f"Viewer running at: {url}")
    print("Browser will open on first plot...")

    print("\nSending plots (Ctrl+C to stop)...\n")

    try:
        # ============================================================
        # SVG Plots (default) - Crisp vector graphics
        # ============================================================

        # Plot 1: Simple line (SVG)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot([0, 1, 2, 3, 4], [0, 1, 4, 9, 16], "b-o", linewidth=2)
        ax.set_title("Plot 1: Quadratic (SVG)")
        ax.set_xlabel("x")
        ax.set_ylabel("y = x²")
        ax.grid(True, alpha=0.3)
        plot_id = viewer.show(fig)  # SVG by default
        print(f"Sent plot 1 (SVG): {plot_id[:8]}...")
        time.sleep(1.5)

        # Plot 2: Sine wave (SVG)
        fig, ax = plt.subplots(figsize=(10, 6))
        x = np.linspace(0, 4 * np.pi, 200)
        ax.plot(x, np.sin(x), "r-", linewidth=2, label="sin(x)")
        ax.plot(x, np.cos(x), "g--", linewidth=2, label="cos(x)")
        ax.set_title("Plot 2: Trigonometry (SVG)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plot_id = viewer.show(fig)
        print(f"Sent plot 2 (SVG): {plot_id[:8]}...")
        time.sleep(1.5)

        # ============================================================
        # PNG Plots - When you need raster output
        # ============================================================

        # Plot 3: Scatter plot (PNG - good for many points)
        fig, ax = plt.subplots(figsize=(10, 6))
        np.random.seed(42)
        x = np.random.randn(500)
        y = x + np.random.randn(500) * 0.5
        colors = np.random.rand(500)
        ax.scatter(x, y, c=colors, cmap="viridis", alpha=0.7, s=30)
        ax.set_title("Plot 3: Scatter (PNG - 500 points)")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        plot_id = viewer.show(fig, format="png")  # Explicit PNG
        print(f"Sent plot 3 (PNG): {plot_id[:8]}...")
        time.sleep(1.5)

        # Plot 4: Heatmap (PNG)
        fig, ax = plt.subplots(figsize=(10, 7))
        data = np.random.rand(20, 20)
        im = ax.imshow(data, cmap="coolwarm")
        ax.set_title("Plot 4: Heatmap (PNG)")
        fig.colorbar(im, ax=ax)
        plot_id = viewer.show(fig, format="png")
        print(f"Sent plot 4 (PNG): {plot_id[:8]}...")
        time.sleep(1.5)

        # ============================================================
        # Animation - Interactive playback in browser
        # ============================================================

        print("\nCreating animation (this takes a moment)...")

        # Animation: Traveling sine wave
        fig, ax = plt.subplots(figsize=(10, 6))
        x = np.linspace(0, 4 * np.pi, 200)
        line, = ax.plot(x, np.sin(x), "b-", linewidth=2)
        ax.set_ylim(-1.5, 1.5)
        ax.set_xlim(0, 4 * np.pi)
        ax.set_title("Animation: Traveling Sine Wave")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.grid(True, alpha=0.3)

        def update(frame):
            line.set_ydata(np.sin(x + frame * 0.1))
            return line,

        anim = animation.FuncAnimation(
            fig, update, frames=60, interval=50, blit=True
        )
        plot_id = viewer.show(anim)
        print(f"Sent animation: {plot_id[:8]}...")

        # ============================================================
        # More SVG examples
        # ============================================================

        time.sleep(1.5)

        # Plot 5: Bar chart (SVG)
        fig, ax = plt.subplots(figsize=(10, 6))
        categories = ["Python", "Rust", "JavaScript", "Go", "C++"]
        values = [85, 92, 78, 81, 75]
        bars = ax.bar(categories, values, color=plt.cm.Set2.colors[:5])
        ax.set_title("Plot 5: Bar Chart (SVG)")
        ax.set_ylabel("Score")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                   str(val), ha="center", va="bottom", fontweight="bold")
        plot_id = viewer.show(fig)
        print(f"Sent plot 5 (SVG): {plot_id[:8]}...")
        time.sleep(1.5)

        # Plot 6: Subplots (SVG)
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        fig.suptitle("Plot 6: Multiple Subplots (SVG)", fontsize=14)

        # Subplot 1: Line
        axes[0, 0].plot(np.linspace(0, 10, 50), np.exp(-np.linspace(0, 10, 50) * 0.3), "m-")
        axes[0, 0].set_title("Exponential Decay")

        # Subplot 2: Histogram
        axes[0, 1].hist(np.random.randn(1000), bins=30, color="teal", alpha=0.7)
        axes[0, 1].set_title("Normal Distribution")

        # Subplot 3: Pie
        axes[1, 0].pie([30, 25, 20, 15, 10], labels=["A", "B", "C", "D", "E"],
                       autopct="%1.0f%%", colors=plt.cm.Pastel1.colors)
        axes[1, 0].set_title("Pie Chart")

        # Subplot 4: Step
        axes[1, 1].step(range(10), np.random.randint(0, 10, 10), where="mid", color="orange")
        axes[1, 1].set_title("Step Plot")

        plt.tight_layout()
        plot_id = viewer.show(fig)
        print(f"Sent plot 6 (SVG): {plot_id[:8]}...")

        print("\n" + "=" * 50)
        print("All plots sent!")
        print("=" * 50)
        print(f"\nView at: {url}")
        print("\nFeatures demonstrated:")
        print("  - SVG output (default): crisp text, zoom without blur")
        print("  - PNG output: for complex plots with many elements")
        print("  - Animation: play/pause, scrub, loop controls")
        print("\nServer continues running in background.")
        print("Use 'rileyviewer stop' to stop it.")
        print("Use 'rileyviewer open' to re-open the browser.")

    except KeyboardInterrupt:
        print("\nInterrupted")


if __name__ == "__main__":
    main()
