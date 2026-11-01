"""Named sketches in matplotlib: outlines, dimension lines and name labels, all in mm.

    from sketch import sheet, panel, shape, dim, radius, name, line, save
    fig, ax = sheet("Bracket - names and sizes (mm)", [["front", "side"]], width_ratios=[2, 1])
    panel(ax["front"], "Bracket - front view")
    shape(ax["front"], cross_section.to_polygons())
    dim(ax["front"], (0, 0), (40, 0), "WIDTH = 40", off=-8)
    name(ax["front"], (20, 10), "slot", (30, 25))
    save(fig, "sketch.png")

Dimension labels carry the generator's parameter name and value, so the user can ask for
a change by name ("WIDTH 50") and it maps to one line in generate.py.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

INK, FILL, DIM, NAME = "#2b2b2b", "#e9e6df", "#b4441c", "#1d5f8a"
MONO = {"fontfamily": "monospace", "fontweight": "bold", "fontsize": 9.5}


def sheet(title, mosaic, subtitle=None, size=(15, 10), **kw):
    """Figure with named panels laid out as in plt.subplot_mosaic, e.g. [["front", "side"], ["front", "detail"]]."""
    fig, axes = plt.subplot_mosaic(mosaic, figsize=size, **kw)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.9, bottom=0.01, wspace=0.04, hspace=0.12)
    fig.suptitle(title, fontsize=17, fontweight="bold", x=0.01, ha="left", y=0.99)
    if subtitle:
        fig.text(0.01, 0.945, subtitle, fontsize=11, color="#555")
    for ax in axes.values():
        ax.set_aspect("equal")
        ax.axis("off")
    return fig, axes


def panel(ax, title):
    ax.set_title(title, fontsize=12, fontweight="bold", loc="left", color=INK)


def shape(ax, polys, fill=FILL, lw=1.4, z=1):
    for p in polys:
        ax.add_patch(Polygon(np.asarray(p), closed=True, fc=fill, ec=INK, lw=lw, zorder=z))
    ax.autoscale_view()


def line(ax, a, b, style="--", color="#888", lw=1):
    ax.plot(*zip(a, b), style, color=color, lw=lw, zorder=2)


def dim(ax, a, b, label, off=10, color=DIM, shift=0, upright=False):
    """Dimension between points a and b, drawn `off` mm to the left of the direction a→b.
    For dimensions too short to hold the label: shift moves it along the line (mm),
    upright puts it horizontally beside the line."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    n = np.array([-d[1], d[0]]) / np.hypot(*d)
    pa, pb = a + n * off, b + n * off
    over = n * np.sign(off) * 2
    for p, q in ((a, pa), (b, pb)):
        ax.plot(*zip(p + n * np.sign(off) * 1, q + over), color=color, lw=0.7, zorder=3)
    ax.annotate("", pb, pa, arrowprops=dict(arrowstyle="<|-|>", color=color, lw=1, shrinkA=0, shrinkB=0,
                                            mutation_scale=9), zorder=3)
    ang = np.degrees(np.arctan2(d[1], d[0]))
    if ang > 90 or ang <= -90:
        ang -= 180 * np.sign(ang)
    at = (pa + pb) / 2 + d / np.hypot(*d) * shift
    if shift:
        end = pb if shift > 0 else pa
        ax.plot(*zip(end, at), color=color, lw=0.7, zorder=3)
    ha = "center"
    if upright:
        out = n * np.sign(off or 1)
        at, ang = at + out * 1.5, 0
        ha = "left" if out[0] > 0.3 else "right" if out[0] < -0.3 else "center"
    ax.text(*at, label, rotation=ang, rotation_mode="anchor", ha=ha, va="center", color=color,
            **MONO, bbox=dict(fc="white", ec="none", pad=1.5), zorder=4)


def radius(ax, center, r, angle, label, color=DIM, text_at=None):
    """Radius line from the centre to the edge at `angle` degrees, label at text_at (or past the edge)."""
    c = np.asarray(center, float)
    u = np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle))])
    ax.annotate("", c + u * r, c, arrowprops=dict(arrowstyle="-|>", color=color, lw=1, shrinkA=0, shrinkB=0,
                                                  mutation_scale=8), zorder=3)
    ax.plot(*c, "o", ms=2.5, color=color, zorder=3)
    t = c + u * (r + 3) if text_at is None else np.asarray(text_at, float)
    ax.annotate(label, c + u * r, t, color=color, **MONO, ha="left" if u[0] >= 0 else "right", va="center",
                arrowprops=None if text_at is None else dict(arrowstyle="-", color=color, lw=0.7), zorder=4)


def name(ax, xy, text, text_at, color=NAME, size=11):
    """Name of a part, face or feature with a leader line pointing at it."""
    ax.plot(*xy, "o", ms=3.5, color=color, zorder=5)
    ax.annotate(text, xy, text_at, color=color, fontsize=size, fontstyle="italic", va="center",
                ha="left" if text_at[0] >= xy[0] else "right",
                arrowprops=dict(arrowstyle="-", color=color, lw=0.8, shrinkA=2, shrinkB=0), zorder=5)


def value(ax, xy, text, text_at, color=DIM):
    """A parameter that has no dimension line (count, list, ratio, text), pointing at where it applies."""
    ax.plot(*xy, "o", ms=3, color=color, zorder=5)
    ax.annotate(text, xy, text_at, color=color, **MONO, va="center", ha="left" if text_at[0] >= xy[0] else "right",
                bbox=dict(fc="white", ec="none", pad=1.5),
                arrowprops=dict(arrowstyle="-", color=color, lw=0.7, shrinkA=2, shrinkB=0), zorder=5)


def save(fig, path, dpi=110):
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
