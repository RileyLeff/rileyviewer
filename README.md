# RILEYVIEWER

This is the first-pass prototype of RileyViewer. I made this because I'm not super fond of the plot-viewing experience in python. A few things I'm nitpicky about:

1. I don't like that plt.show() in the matplotlib-universe (seaborn etc) hangs your program and wants user interaction to proceed.
2. I don't like that LLMs leave .pngs saved all over my project to avoid this.
3. I don't like the hidden side-effects and implicit state used in matplotlib-based libraries.
4. I don't like viewing plots in my IDE, I prefer throwing them in the browser.

As much as I dislike R, I really really like httpgd. I want something like httpgd in python, but I wasn't stoked about the existing set of plot viewers.

The idea here is just to pipe the plot output to a browser window. Eventually this will be able to handle a variety of plotting backends. For seaborn/mpl, to get around the state stuff (plt.close(), etc) you can basically hit a with block:

```python
from rileyviewer import Viewer
import matplotlib.pyplot as plt

viewer = Viewer()

with viewer.capture() as ctx:
    plt.plot([1, 2, 3], [1, 4, 9])
    plt.title("My Plot")
    ctx.push()  # sends the current figure to the browser

    plt.figure()  # start a new figure
    plt.scatter([1, 2, 3], [3, 2, 1])
    ctx.push()  # sends this one too

# plt.close("all") is called automatically on exit
```

Or if you prefer explicit control:

```python
from rileyviewer import Viewer
import matplotlib.pyplot as plt

viewer = Viewer()

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
viewer.show(fig)
plt.close(fig)
```

That I actually quite like the semantics of -- it separates out the plot viewing and makes the end of the with block context the end of the plot state stuff. I will likely incrementally add features and fix bugs as I encounter them. If this ends up getting useful I might eventually throw it on pypi and crates.io, idk!