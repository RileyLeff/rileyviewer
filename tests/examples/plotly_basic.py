#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "plotly",
#   "numpy",
#   "rileyviewer @ file:///${PROJECT_ROOT}/python",
# ]
# ///
"""
Plotly interactive chart examples.

Usage:
    uv run tests/examples/plotly_basic.py
"""

import plotly.graph_objects as go
import plotly.express as px
import numpy as np

from rileyviewer import Viewer


def main():
    viewer = Viewer()
    print(f"Viewer at: http://{viewer.addr}/?token={viewer.token}")

    # 1. Simple line chart
    fig1 = go.Figure()
    x = np.linspace(0, 10, 100)
    fig1.add_trace(go.Scatter(x=x, y=np.sin(x), mode='lines', name='sin(x)'))
    fig1.add_trace(go.Scatter(x=x, y=np.cos(x), mode='lines', name='cos(x)'))
    fig1.update_layout(title='Interactive Sine/Cosine', xaxis_title='x', yaxis_title='y')
    plot_id = viewer.show(fig1)
    print(f"Sent line chart: {plot_id[:8]}...")

    # 2. Scatter plot with hover info
    np.random.seed(42)
    n = 100
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=np.random.randn(n),
        y=np.random.randn(n),
        mode='markers',
        marker=dict(
            size=np.random.uniform(5, 20, n),
            color=np.random.randn(n),
            colorscale='Viridis',
            showscale=True
        ),
        text=[f'Point {i}' for i in range(n)],
        hovertemplate='<b>%{text}</b><br>x: %{x:.2f}<br>y: %{y:.2f}<extra></extra>'
    ))
    fig2.update_layout(title='Scatter with Hover Info')
    plot_id = viewer.show(fig2)
    print(f"Sent scatter plot: {plot_id[:8]}...")

    # 3. 3D surface plot
    x = np.linspace(-5, 5, 50)
    y = np.linspace(-5, 5, 50)
    X, Y = np.meshgrid(x, y)
    Z = np.sin(np.sqrt(X**2 + Y**2))

    fig3 = go.Figure(data=[go.Surface(z=Z, x=X, y=Y, colorscale='RdBu')])
    fig3.update_layout(
        title='3D Surface (drag to rotate)',
        scene=dict(xaxis_title='X', yaxis_title='Y', zaxis_title='Z')
    )
    plot_id = viewer.show(fig3)
    print(f"Sent 3D surface: {plot_id[:8]}...")

    # 4. Bar chart with animation-ready data
    categories = ['A', 'B', 'C', 'D', 'E']
    values = [23, 45, 56, 78, 32]
    fig4 = go.Figure(data=[
        go.Bar(x=categories, y=values, marker_color='steelblue')
    ])
    fig4.update_layout(title='Bar Chart', xaxis_title='Category', yaxis_title='Value')
    plot_id = viewer.show(fig4)
    print(f"Sent bar chart: {plot_id[:8]}...")

    # 5. Heatmap
    z = np.random.rand(10, 10)
    fig5 = go.Figure(data=go.Heatmap(z=z, colorscale='Viridis'))
    fig5.update_layout(title='Heatmap')
    plot_id = viewer.show(fig5)
    print(f"Sent heatmap: {plot_id[:8]}...")

    print("\n--- All Plotly plots sent! ---")
    print("Try interacting with them in the browser:")
    print("  - Hover for tooltips")
    print("  - Drag to pan, scroll to zoom")
    print("  - Drag the 3D surface to rotate")
    print("\nUse 'rileyviewer stop' to stop the server.")


if __name__ == "__main__":
    main()
