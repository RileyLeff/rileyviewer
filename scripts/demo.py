# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "rileyviewer",
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "plotly",
#     "altair",
#     "vl-convert-python",
# ]
# [tool.uv.sources]
# rileyviewer = { path = "../python" }
# ///
"""Demo script that sends a variety of plots to a running rileyviewer server.

Usage:
    uv run scripts/demo.py

Make sure the server is running first:
    cargo run --release --features embed-assets -- serve
"""

import time
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd

matplotlib.use("Agg")

from rileyviewer import Viewer

v = Viewer()
print(f"Connected to rileyviewer at {v.addr}")


# --- 1. Matplotlib: basic line plot ---
print("Sending matplotlib line plot...")
fig, ax = plt.subplots(figsize=(8, 5))
x = np.linspace(0, 4 * np.pi, 200)
ax.plot(x, np.sin(x), label="sin(x)", linewidth=2)
ax.plot(x, np.cos(x), label="cos(x)", linewidth=2, linestyle="--")
ax.set_title("Trigonometric Functions")
ax.set_xlabel("x")
ax.set_ylabel("y")
ax.legend()
ax.grid(True, alpha=0.3)
v.show(fig, title="Trig functions", tags=["matplotlib", "math"])
plt.close(fig)
time.sleep(0.3)


# --- 2. Matplotlib: scatter plot with colormap ---
print("Sending matplotlib scatter plot...")
fig, ax = plt.subplots(figsize=(8, 6))
rng = np.random.default_rng(42)
n = 300
x = rng.standard_normal(n)
y = 0.5 * x + rng.standard_normal(n) * 0.5
colors = np.sqrt(x**2 + y**2)
sc = ax.scatter(x, y, c=colors, cmap="viridis", alpha=0.7, s=30)
fig.colorbar(sc, ax=ax, label="Distance from origin")
ax.set_title("Correlated Scatter")
ax.set_xlabel("x")
ax.set_ylabel("y")
v.show(fig, title="Correlated scatter", tags=["matplotlib", "scatter"])
plt.close(fig)
time.sleep(0.3)


# --- 3. Matplotlib: histogram ---
print("Sending matplotlib histogram...")
fig, ax = plt.subplots(figsize=(8, 5))
data = rng.standard_normal(1000)
ax.hist(data, bins=40, color="#4f46e5", alpha=0.7, edgecolor="white", linewidth=0.5)
ax.axvline(data.mean(), color="red", linestyle="--", label=f"mean = {data.mean():.2f}")
ax.set_title("Normal Distribution (n=1000)")
ax.set_xlabel("Value")
ax.set_ylabel("Count")
ax.legend()
v.show(fig, title="Histogram", tags=["matplotlib", "stats"])
plt.close(fig)
time.sleep(0.3)


# --- 4. Matplotlib: subplots grid ---
print("Sending matplotlib subplots...")
fig, axes = plt.subplots(2, 2, figsize=(10, 8))
# Top left: bar chart
categories = ["A", "B", "C", "D", "E"]
values = rng.integers(10, 50, size=5)
axes[0, 0].bar(categories, values, color=["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6"])
axes[0, 0].set_title("Bar Chart")
# Top right: pie chart
axes[0, 1].pie(values, labels=categories, autopct="%1.0f%%", startangle=90)
axes[0, 1].set_title("Pie Chart")
# Bottom left: box plot
box_data = [rng.standard_normal(50) + i for i in range(4)]
axes[1, 0].boxplot(box_data, labels=["G1", "G2", "G3", "G4"])
axes[1, 0].set_title("Box Plot")
# Bottom right: heatmap
matrix = rng.standard_normal((8, 8))
im = axes[1, 1].imshow(matrix, cmap="RdBu_r", aspect="auto")
fig.colorbar(im, ax=axes[1, 1])
axes[1, 1].set_title("Heatmap")
fig.tight_layout()
v.show(fig, title="Subplot grid", tags=["matplotlib", "multi"])
plt.close(fig)
time.sleep(0.3)


# --- 5. Matplotlib as PNG (raster) ---
print("Sending matplotlib PNG...")
fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
t = np.linspace(0, 10, 500)
ax.fill_between(t, np.sin(t) * np.exp(-0.1 * t), alpha=0.5, label="Damped sine")
ax.fill_between(t, -np.cos(t) * np.exp(-0.1 * t), alpha=0.5, label="Damped cosine")
ax.set_title("Damped Oscillations")
ax.legend()
v.show(fig, format="png", title="Damped oscillations (PNG)", tags=["matplotlib", "png"])
plt.close(fig)
time.sleep(0.3)


# --- 6. Plotly: interactive scatter ---
print("Sending Plotly scatter...")
import plotly.express as px

df_iris = px.data.iris()
fig_plotly = px.scatter(
    df_iris,
    x="sepal_width",
    y="sepal_length",
    color="species",
    size="petal_length",
    hover_data=["petal_width"],
    title="Iris Dataset",
)
v.show(fig_plotly, title="Iris scatter (Plotly)", tags=["plotly", "interactive"])
time.sleep(0.3)


# --- 7. Plotly: 3D surface ---
print("Sending Plotly 3D surface...")
import plotly.graph_objects as go

x_surf = np.linspace(-5, 5, 50)
y_surf = np.linspace(-5, 5, 50)
X, Y = np.meshgrid(x_surf, y_surf)
Z = np.sin(np.sqrt(X**2 + Y**2))
fig_3d = go.Figure(data=[go.Surface(z=Z, x=X, y=Y, colorscale="Viridis")])
fig_3d.update_layout(title="3D Surface", scene=dict(xaxis_title="X", yaxis_title="Y", zaxis_title="Z"))
v.show(fig_3d, title="3D surface (Plotly)", tags=["plotly", "3d"])
time.sleep(0.3)


# --- 8. Plotly: bar chart ---
print("Sending Plotly bar chart...")
df_tips = px.data.tips()
fig_bar = px.bar(df_tips, x="day", y="total_bill", color="sex", barmode="group", title="Tips by Day")
v.show(fig_bar, title="Tips bar chart (Plotly)", tags=["plotly", "bar"])
time.sleep(0.3)


# --- 9. Altair / Vega-Lite: interactive chart ---
print("Sending Altair chart...")
import altair as alt

source = pd.DataFrame({
    "x": rng.standard_normal(200),
    "y": rng.standard_normal(200),
    "category": rng.choice(["A", "B", "C"], 200),
})

chart = alt.Chart(source).mark_circle(size=60).encode(
    x="x:Q",
    y="y:Q",
    color="category:N",
    tooltip=["x", "y", "category"],
).properties(title="Random Clusters (Altair)", width=400, height=300).interactive()
v.show(chart, title="Random clusters (Altair)", tags=["altair", "vega"])
time.sleep(0.3)


# --- 10. Altair: layered chart ---
print("Sending Altair layered chart...")
dates = pd.date_range("2024-01-01", periods=90, freq="D")
stock = pd.DataFrame({
    "date": dates,
    "price": 100 + np.cumsum(rng.standard_normal(90) * 2),
})
stock["MA7"] = stock["price"].rolling(7).mean()
stock["MA30"] = stock["price"].rolling(30).mean()

base = alt.Chart(stock).encode(x="date:T")
line = base.mark_line(color="#3b82f6").encode(y="price:Q")
ma7 = base.mark_line(color="#f59e0b", strokeDash=[5, 3]).encode(y="MA7:Q")
ma30 = base.mark_line(color="#ef4444", strokeDash=[2, 2]).encode(y="MA30:Q")
layered = (line + ma7 + ma30).properties(title="Stock Price with Moving Averages", width=500, height=300)
v.show(layered, title="Stock with MAs (Altair)", tags=["altair", "vega", "timeseries"])
time.sleep(0.3)


# --- 11. Pandas DataFrame ---
print("Sending pandas DataFrame...")
df = pd.DataFrame({
    "Name": ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank"],
    "Age": [28, 35, 42, 31, 26, 45, 33, 29],
    "Score": [92.5, 87.3, 95.1, 78.6, 88.9, 91.2, 85.7, 93.4],
    "Department": ["Engineering", "Marketing", "Engineering", "Sales", "Engineering", "Marketing", "Sales", "Engineering"],
    "Hired": pd.date_range("2020-01-15", periods=8, freq="3ME"),
})
v.show(df, title="Employee data", tags=["table", "pandas"])
time.sleep(0.3)


# --- 12. Larger DataFrame ---
print("Sending larger DataFrame...")
big_df = pd.DataFrame({
    "id": range(500),
    "value_a": rng.standard_normal(500).round(3),
    "value_b": rng.uniform(0, 100, 500).round(2),
    "category": rng.choice(["alpha", "beta", "gamma", "delta"], 500),
    "flag": rng.choice([True, False], 500),
})
v.show(big_df, title="500-row dataset", tags=["table", "pandas", "large"])
time.sleep(0.3)


# --- 13. HTML content ---
print("Sending HTML content...")
html = """
<!DOCTYPE html>
<html>
<head><style>
body { font-family: system-ui; background: #0f172a; color: #e2e8f0; padding: 2rem; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
h1 { font-size: 2.5rem; background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
p { color: #94a3b8; font-size: 1.1rem; max-width: 500px; text-align: center; line-height: 1.6; }
.badge { display: inline-block; background: #1e293b; border: 1px solid #334155; border-radius: 9999px; padding: 0.25rem 0.75rem; font-size: 0.875rem; color: #10b981; margin-top: 1rem; }
</style></head>
<body>
<h1>rileyviewer</h1>
<p>This is a raw HTML plot. You can send any HTML content — interactive widgets, D3 visualizations, styled reports, or custom dashboards.</p>
<span class="badge">HTML type</span>
</body>
</html>
"""
v.send_html(html, title="HTML demo", tags=["html", "custom"])
time.sleep(0.3)


# --- 14. Vega-Lite JSON directly ---
print("Sending Vega-Lite spec directly...")
vega_spec = json.dumps({
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "description": "A bar chart with highlighting on hover",
    "data": {
        "values": [
            {"language": "Python", "users": 48},
            {"language": "JavaScript", "users": 38},
            {"language": "TypeScript", "users": 25},
            {"language": "Rust", "users": 12},
            {"language": "Go", "users": 15},
            {"language": "Julia", "users": 5},
        ]
    },
    "width": 300,
    "height": 200,
    "mark": {"type": "bar", "cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4},
    "encoding": {
        "x": {"field": "language", "type": "nominal", "sort": "-y"},
        "y": {"field": "users", "type": "quantitative", "title": "Users (millions)"},
        "color": {"field": "language", "type": "nominal", "legend": None},
    },
})
v.send_vega_json(vega_spec, title="Language popularity (Vega)", tags=["vega", "bar"])
time.sleep(0.3)


# --- 15. Another Vega spec with hardcoded dimensions (tests responsive sizing) ---
print("Sending Vega-Lite with hardcoded 400x200 (tests responsive override)...")
vega_small = json.dumps({
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "description": "This spec has hardcoded width:400, height:200 — viewer should override to fill container",
    "width": 400,
    "height": 200,
    "data": {
        "values": [{"x": i, "y": np.sin(i / 5).item()} for i in range(50)]
    },
    "mark": "line",
    "encoding": {
        "x": {"field": "x", "type": "quantitative"},
        "y": {"field": "y", "type": "quantitative"},
    },
})
v.send_vega_json(vega_small, title="Hardcoded 400x200 (should fill)", tags=["vega", "sizing-test"])
time.sleep(0.3)


# --- 16. Plot with notes ---
print("Sending plot with notes...")
fig, ax = plt.subplots(figsize=(7, 5))
x = np.linspace(0, 10, 100)
ax.plot(x, np.exp(-0.3 * x) * np.sin(2 * x), "b-", linewidth=2)
ax.set_title("Damped Oscillator")
ax.set_xlabel("Time")
ax.set_ylabel("Amplitude")
ax.grid(True, alpha=0.3)
v.show(
    fig,
    title="Damped oscillator",
    notes="Exponential decay envelope with sinusoidal carrier. Hover the (i) icon to see this note!",
    tags=["matplotlib", "physics", "notes-test"],
)
plt.close(fig)
time.sleep(0.3)


# --- 17. Multiple plots with same tags (for multi-tag filter testing) ---
print("Sending tagged experiment plots...")
for exp_name, color in [("baseline", "#6366f1"), ("treatment-A", "#10b981"), ("treatment-B", "#f59e0b")]:
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.linspace(0, 5, 100)
    offset = {"baseline": 0, "treatment-A": 0.5, "treatment-B": -0.3}[exp_name]
    ax.plot(x, np.log1p(x) + offset + rng.standard_normal(100) * 0.1, color=color, linewidth=2)
    ax.set_title(f"Experiment: {exp_name}")
    ax.set_xlabel("Dose")
    ax.set_ylabel("Response")
    ax.grid(True, alpha=0.3)
    v.show(fig, title=f"{exp_name} response curve", tags=["experiment", exp_name])
    plt.close(fig)
    time.sleep(0.2)


print(f"\nDone! Sent 18 items to rileyviewer.")
print("Try: multi-select tags, presentation mode, export menu, notes (i) icon, Vega sizing")
