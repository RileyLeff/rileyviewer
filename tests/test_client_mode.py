#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "matplotlib",
#   "rileyviewer @ file:///${PROJECT_ROOT}/python",
# ]
# ///
"""Test that client mode works: second Viewer connects to existing server."""

import os
import sys
import time
import subprocess

os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.getcwd(), ".mplconfig"))


def main():
    # Use a known token for testing
    TEST_TOKEN = "test-token-12345"

    # Start server in a subprocess with known token
    server_proc = subprocess.Popen(
        [sys.executable, "-c", f"""
import time
from rileyviewer import Viewer
v = Viewer(open_browser=False, token="{TEST_TOKEN}")
print(f"SERVER: running at {{v.addr}}, token={{v.token}}", flush=True)
time.sleep(10)
v.shutdown()
print("SERVER: shutdown", flush=True)
"""],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server to start
    line = server_proc.stdout.readline()
    print(line.strip())
    time.sleep(0.5)

    # Now create a second Viewer that should connect as client with same token
    from rileyviewer import Viewer
    v2 = Viewer(open_browser=False, token=TEST_TOKEN)
    print(f"CLIENT: addr={v2.addr}, client_mode={v2._client_mode}")

    if not v2._client_mode:
        print("ERROR: v2 should be in client mode!")
        server_proc.terminate()
        sys.exit(1)

    # Send a plot via HTTP
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    plot_id = v2.show(fig)
    print(f"CLIENT: sent plot via HTTP: {plot_id}")

    # Wait for server to finish
    server_proc.terminate()
    server_proc.wait()
    print("SUCCESS: client mode works!")


if __name__ == "__main__":
    main()
