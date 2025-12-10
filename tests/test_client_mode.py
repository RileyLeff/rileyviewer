#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "matplotlib",
#   "rileyviewer @ file:///${PROJECT_ROOT}/python",
# ]
# ///
"""Test that server reuse works: second Viewer connects to existing server.

This test verifies that:
1. First Viewer starts a detached server
2. Second Viewer connects to the same server (doesn't start a new one)
3. Both viewers can send plots successfully
"""

import os
import sys

os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.getcwd(), ".mplconfig"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    from rileyviewer import Viewer
    from rileyviewer.viewer import _check_server_running, DEFAULT_HOST, DEFAULT_PORT

    # Ensure no server is running initially
    if _check_server_running(DEFAULT_HOST, DEFAULT_PORT):
        print("NOTE: Server already running, will reuse it")

    # First viewer - starts server if not running
    v1 = Viewer(open_browser=False)
    print(f"VIEWER 1: addr={v1.addr}, token={v1.token[:8]}...")

    # Second viewer - should connect to existing server
    v2 = Viewer(open_browser=False)
    print(f"VIEWER 2: addr={v2.addr}, token={v2.token[:8]}...")

    # Verify both viewers have the same token (from the same server)
    if v1.token != v2.token:
        print(f"ERROR: tokens don't match!")
        print(f"  v1.token = {v1.token}")
        print(f"  v2.token = {v2.token}")
        sys.exit(1)

    # Send plots from both viewers
    fig1, ax1 = plt.subplots()
    ax1.plot([1, 2, 3], [1, 4, 9])
    ax1.set_title("From Viewer 1")
    plot_id1 = v1.show(fig1)
    print(f"VIEWER 1: sent plot {plot_id1[:8]}...")

    fig2, ax2 = plt.subplots()
    ax2.plot([1, 2, 3], [9, 4, 1])
    ax2.set_title("From Viewer 2")
    plot_id2 = v2.show(fig2)
    print(f"VIEWER 2: sent plot {plot_id2[:8]}...")

    print("SUCCESS: server reuse works!")
    print("NOTE: Server is still running. Use 'rileyviewer stop' to stop it.")


if __name__ == "__main__":
    main()
