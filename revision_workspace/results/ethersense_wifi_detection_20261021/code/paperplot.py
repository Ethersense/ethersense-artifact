"""paperplot -- publication figure kit for MobiCom / NSDI / USENIX Security / NeurIPS-class papers.

Design goals (see ../figures/FIGURES.md for the rationale and corpus statistics):
  * the figure is created at its *printed* size, so 8 pt in matplotlib is 8 pt in the PDF;
  * one consistent look across every figure of a paper (fonts, line widths, colours, "ours" colour);
  * colour is never the only cue: every series also gets a marker / line style / hatch;
  * vector PDF with TrueType (Type 42) fonts -- no Type 3 fonts, no rasterised text;
  * a built-in lint pass that catches the defects reviewers notice: overlapping or clipped labels,
    text smaller than the venue minimum, too many colours, legends covering data.

Usage
-----
    import sys; sys.path.insert(0, r"D:\\Users\\user1\\.claude\\skills\\topconf-writer\\figures")
    import paperplot as pp
    fig, ax = pp.figure("mobicom", span="column", aspect=0.6)
    pp.cdf(ax, {"Ours": err_ours, "Baseline A": err_a}, ours="Ours", xlabel="Localization error (cm)")
    pp.save(fig, "figures/fig_error_cdf")          # writes .pdf + .png and prints the lint report

Everything is plain matplotlib underneath; pass extra kwargs straight through when you need to.
"""
from __future__ import annotations

import math
import os
from typing import Dict, Iterable, Optional, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

# ----------------------------------------------------------------------------------------------
# Venue geometry (inches). Verify against the template with \the\columnwidth / \the\textwidth.
# ----------------------------------------------------------------------------------------------
LAYOUTS = {
    # ACM acmart sigconf (MobiCom, SIGCOMM, CCS, MobiSys, SenSys): 7.0in text block, 0.33in gutter.
    "acm": {"column": 3.33, "text": 7.0, "body_pt": 10, "serif": ["Linux Libertine O", "Linux Libertine", "Libertinus Serif", "Times New Roman", "Liberation Serif", "DejaVu Serif"]},
    # USENIX two-column (NSDI, USENIX Security, OSDI): 7in x 9in block, 0.33in gutter, Times 10pt.
    "usenix": {"column": 3.33, "text": 7.0, "body_pt": 10, "serif": ["Times New Roman", "Times", "Nimbus Roman", "Liberation Serif", "DejaVu Serif"]},
    # IEEE conference (S&P, NDSS, INFOCOM): 3.5in columns, 7.16in text width.
    "ieee": {"column": 3.5, "text": 7.16, "body_pt": 10, "serif": ["Times New Roman", "Times", "Nimbus Roman", "Liberation Serif", "DejaVu Serif"]},
    # NeurIPS / ICLR single column, 5.5in text width.
    "neurips": {"column": 5.5, "text": 5.5, "body_pt": 10, "serif": ["Times New Roman", "Times", "Nimbus Roman", "Liberation Serif", "DejaVu Serif"]},
    # ICML two-column.
    "icml": {"column": 3.25, "text": 6.75, "body_pt": 10, "serif": ["Times New Roman", "Times", "Liberation Serif", "DejaVu Serif"]},
    # ACM acmsmall (IMWUT / journals): single column ~5.47in.
    "acmsmall": {"column": 5.47, "text": 5.47, "body_pt": 10, "serif": ["Linux Libertine O", "Libertinus Serif", "Times New Roman", "DejaVu Serif"]},
}
VENUE_LAYOUT = {
    "mobicom": "acm", "sigcomm": "acm", "ccs": "acm", "mobisys": "acm", "sensys": "acm", "ubicomp": "acmsmall",
    "imwut": "acmsmall", "nsdi": "usenix", "usenixsec": "usenix", "usenix": "usenix", "osdi": "usenix",
    "sp": "ieee", "oakland": "ieee", "ndss": "ieee", "infocom": "ieee", "ieee": "ieee",
    "neurips": "neurips", "iclr": "neurips", "icml": "icml", "acm": "acm", "acmsmall": "acmsmall",
}
SANS = ["Helvetica", "Arial", "Liberation Sans", "Nimbus Sans", "DejaVu Sans"]

# ----------------------------------------------------------------------------------------------
# Colour system. Okabe-Ito and Paul Tol palettes are colour-blind safe; "ours" gets the warm accent,
# baselines get cool / neutral tones so the reader's eye lands on the contribution first.
# ----------------------------------------------------------------------------------------------
OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
TOL_BRIGHT = ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"]
TOL_MUTED = ["#332288", "#88CCEE", "#44AA99", "#117733", "#999933", "#DDCC77", "#CC6677", "#882255", "#AA4499"]
OURS = "#D55E00"                 # vermillion: survives deuteranopia/protanopia and grayscale (dark)
BASELINES = ["#0072B2", "#56B4E9", "#009E73", "#7F7F7F", "#CC79A7", "#E69F00", "#332288"]
NEUTRALS = ["#4D4D4D", "#808080", "#B3B3B3", "#D9D9D9"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
LINESTYLES = ["-", "--", "-.", ":", (0, (5, 1.5, 1, 1.5)), (0, (1, 1))]
HATCHES = ["", "///", "\\\\\\", "xxx", "...", "+++", "---", "ooo"]
SEQ_CMAP = "viridis"             # perceptually uniform; "cividis" for strict CVD safety
DIV_CMAP = "RdBu_r"              # diverging around a meaningful zero

MIN_TEXT_PT = 6.0                # hard floor (printed); most venues ask "legible when printed"
WARN_TEXT_PT = 7.0               # corpus median of the smallest figure text in award papers is ~7-8 pt


def layout(venue: str) -> dict:
    key = VENUE_LAYOUT.get(venue.lower(), venue.lower())
    if key not in LAYOUTS:
        raise ValueError(f"unknown venue/layout {venue!r}; known: {sorted(VENUE_LAYOUT)}")
    return LAYOUTS[key]


def style(venue: str = "mobicom", font: str = "sans", base: float = 8.0) -> dict:
    """rcParams for printed-size figures. font='sans' (default, best legibility at 7-8 pt) or 'serif'
    (match the body text; use consistently for every figure of the paper)."""
    lay = layout(venue)
    fam = SANS if font == "sans" else lay["serif"]
    rc = {
        "font.family": "sans-serif" if font == "sans" else "serif",
        "font.sans-serif": SANS, "font.serif": lay["serif"],
        "mathtext.fontset": "stixsans" if font == "sans" else "stix",
        "font.size": base, "axes.labelsize": base, "axes.titlesize": base,
        "xtick.labelsize": base - 1, "ytick.labelsize": base - 1, "legend.fontsize": base - 1,
        "axes.linewidth": 0.6, "axes.edgecolor": "#333333", "axes.labelcolor": "#111111",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#D9D9D9", "grid.linewidth": 0.4,
        "grid.linestyle": "--", "axes.axisbelow": True,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.minor.width": 0.4, "ytick.minor.width": 0.4, "xtick.color": "#333333", "ytick.color": "#333333",
        "lines.linewidth": 1.3, "lines.markersize": 3.6, "lines.markeredgewidth": 0.6,
        "patch.linewidth": 0.5, "hatch.linewidth": 0.5,
        "errorbar.capsize": 1.8,
        "legend.frameon": False, "legend.handlelength": 1.8, "legend.handletextpad": 0.4,
        "legend.columnspacing": 1.0, "legend.borderaxespad": 0.2, "legend.labelspacing": 0.25,
        "figure.dpi": 150, "savefig.dpi": 600, "savefig.bbox": "tight", "savefig.pad_inches": 0.015,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "axes.prop_cycle": mpl.cycler(color=BASELINES),
        "image.cmap": SEQ_CMAP,
    }
    rc["_family_list"] = fam  # informational
    return rc


def figure(venue: str = "mobicom", span: str = "column", aspect: float = 0.62, nrows: int = 1,
           ncols: int = 1, font: str = "sans", base: float = 8.0, width: Optional[float] = None,
           height: Optional[float] = None, **subplot_kw):
    """Create a figure at its printed size. span: 'column' | 'text' | float fraction of text width
    (e.g. 0.48 for a sub-figure placed side by side in a column)."""
    lay = layout(venue)
    if width is None:
        if span == "column":
            width = lay["column"]
        elif span == "text":
            width = lay["text"]
        else:
            width = float(span) * lay["text"]
    if height is None:
        height = width * aspect * (nrows / max(1, ncols)) ** 0.5 if nrows > 1 else width * aspect
    rc = {k: v for k, v in style(venue, font, base).items() if not k.startswith("_")}
    mpl.rcParams.update(rc)
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height), layout="constrained", **subplot_kw)
    fig._paperplot = {"venue": venue, "width_in": width, "base": base}
    return fig, axes


# ----------------------------------------------------------------------------------------------
# Series styling: deterministic, so the same method has the same look in every figure.
# ----------------------------------------------------------------------------------------------
_ASSIGNED: Dict[str, dict] = {}


def series_style(name: str, ours: Optional[str] = None, index: Optional[int] = None) -> dict:
    """Stable style per series name across all figures of a paper (call order independent once
    assigned). The 'ours' series is always vermillion, solid, circle, drawn on top."""
    if name == ours:
        return {"color": OURS, "marker": "o", "linestyle": "-", "hatch": "", "zorder": 5, "linewidth": 1.6}
    if name not in _ASSIGNED:
        i = len(_ASSIGNED) if index is None else index
        _ASSIGNED[name] = {"color": BASELINES[i % len(BASELINES)], "marker": MARKERS[(i + 1) % len(MARKERS)],
                           "linestyle": LINESTYLES[(i + 1) % len(LINESTYLES)], "hatch": HATCHES[(i + 1) % len(HATCHES)],
                           "zorder": 3, "linewidth": 1.2}
    return dict(_ASSIGNED[name])


def reset_styles():
    _ASSIGNED.clear()


# ----------------------------------------------------------------------------------------------
# Plot templates
# ----------------------------------------------------------------------------------------------
def cdf(ax, data: Dict[str, Sequence[float]], ours: Optional[str] = None, xlabel: str = "", ylabel: str = "CDF",
        log: bool = False, mark_median: bool = False, xlim=None):
    """Empirical CDFs (step lines). Typical for latency / error distributions in systems papers."""
    for name, vals in data.items():
        v = np.sort(np.asarray(vals, dtype=float))
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        y = np.arange(1, v.size + 1) / v.size
        st = series_style(name, ours)
        ax.step(v, y, where="post", color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"],
                label=name, zorder=st["zorder"])
        if mark_median:
            med = float(np.median(v))
            ax.plot([med], [0.5], marker=st["marker"], color=st["color"], zorder=st["zorder"] + 1, markersize=3.2)
    if log:
        ax.set_xscale("log")
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    if xlim:
        ax.set_xlim(*xlim)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="both")
    return ax


def grouped_bars(ax, categories: Sequence[str], series: Dict[str, Sequence[float]], errors: Optional[Dict[str, Sequence[float]]] = None,
                 ours: Optional[str] = None, ylabel: str = "", value_labels: bool = False, fmt: str = "{:.1f}",
                 hatch: bool = True, width: float = 0.8, ylim=None):
    """Grouped bars with optional error bars and hatches (grayscale-safe). Bars start at zero."""
    n = len(series)
    x = np.arange(len(categories))
    bw = width / max(1, n)
    for i, (name, vals) in enumerate(series.items()):
        st = series_style(name, ours)
        off = (i - (n - 1) / 2) * bw
        err = None if errors is None else errors.get(name)
        bars = ax.bar(x + off, vals, bw * 0.92, label=name, color=st["color"], edgecolor="#222222",
                      linewidth=0.4, hatch=(st["hatch"] if hatch and name != ours else ""), zorder=st["zorder"],
                      yerr=err, error_kw={"elinewidth": 0.6, "capthick": 0.6, "ecolor": "#222222"})
        if value_labels:
            for b, v in zip(bars, vals):
                ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, b.get_height()), xytext=(0, 1.5),
                            textcoords="offset points", ha="center", va="bottom", fontsize=mpl.rcParams["font.size"] - 1)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel(ylabel)
    ax.set_ylim(bottom=0)
    if ylim:
        ax.set_ylim(*ylim)
    ax.tick_params(axis="x", length=0)
    return ax


def lines(ax, x: Sequence[float], series: Dict[str, Sequence[float]], ci: Optional[Dict[str, Sequence[Sequence[float]]]] = None,
          ours: Optional[str] = None, xlabel: str = "", ylabel: str = "", markevery=None, logx=False, logy=False):
    """Line plot with markers on every series and optional CI bands {name: (low, high)}."""
    x = np.asarray(x)
    for name, ys in series.items():
        st = series_style(name, ours)
        ax.plot(x, ys, color=st["color"], linestyle=st["linestyle"], marker=st["marker"], label=name,
                linewidth=st["linewidth"], zorder=st["zorder"], markevery=markevery,
                markerfacecolor="white" if name != ours else st["color"])
        if ci and name in ci:
            lo, hi = ci[name]
            ax.fill_between(x, lo, hi, color=st["color"], alpha=0.15, linewidth=0, zorder=st["zorder"] - 1)
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    return ax


def stacked_breakdown(ax, categories: Sequence[str], parts: Dict[str, Sequence[float]], ylabel: str = "",
                      horizontal: bool = False, colors: Optional[Sequence[str]] = None, percent: bool = False):
    """Stacked bars for latency / energy / error breakdowns (prefer over pie charts)."""
    data = np.array(list(parts.values()), dtype=float)
    if percent:
        data = 100 * data / data.sum(axis=0, keepdims=True)
    base = np.zeros(data.shape[1])
    cols = colors or (TOL_MUTED if len(parts) > 6 else OKABE_ITO)
    for i, (name, row) in enumerate(zip(parts.keys(), data)):
        kw = dict(color=cols[i % len(cols)], edgecolor="white", linewidth=0.5, label=name, hatch=HATCHES[i % len(HATCHES)])
        if horizontal:
            ax.barh(categories, row, left=base, **kw)
        else:
            ax.bar(categories, row, bottom=base, **kw)
        base += row
    (ax.set_xlabel if horizontal else ax.set_ylabel)(ylabel + (" (%)" if percent and "%" not in ylabel else ""))
    return ax


def heatmap(ax, matrix, xlabels: Sequence[str], ylabels: Sequence[str], cmap: str = SEQ_CMAP, annotate: bool = True,
            fmt: str = "{:.2f}", vmin=None, vmax=None, cbar_label: str = "", diverging_center: Optional[float] = None):
    """Square-cell heatmap / confusion matrix with in-cell values (white/black text chosen by luminance)."""
    m = np.asarray(matrix, dtype=float)
    norm = None
    if diverging_center is not None:
        norm = mpl.colors.TwoSlopeNorm(vcenter=diverging_center, vmin=vmin, vmax=vmax)
        cmap = DIV_CMAP if cmap == SEQ_CMAP else cmap
    im = ax.imshow(m, cmap=cmap, vmin=None if norm else vmin, vmax=None if norm else vmax, norm=norm, aspect="equal")
    ax.set_xticks(range(len(xlabels)), labels=xlabels)
    ax.set_yticks(range(len(ylabels)), labels=ylabels)
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    if annotate:
        cm = im.cmap
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                r, g, b, _ = cm(im.norm(m[i, j]))
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                ax.text(j, i, fmt.format(m[i, j]), ha="center", va="center",
                        color="black" if lum > 0.55 else "white", fontsize=mpl.rcParams["font.size"] - 1)
    cb = ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(width=0.4, length=2)
    if cbar_label:
        cb.set_label(cbar_label)
    return im


def tradeoff(ax, points: Dict[str, Sequence[float]], ours: Optional[str] = None, xlabel: str = "", ylabel: str = "",
             better: str = "upper left", pareto: bool = False, annotate: bool = True):
    """Scatter of methods in a cost-quality plane, with an optional Pareto frontier and a 'Better' arrow.
    better: corner that is better, e.g. 'upper left' = high y, low x."""
    xs, ys = [], []
    for name, (x, y) in points.items():
        st = series_style(name, ours)
        ax.scatter([x], [y], s=28 if name == ours else 20, marker=st["marker"], color=st["color"],
                   edgecolor="#222222", linewidth=0.4, zorder=st["zorder"], label=name)
        if annotate:
            ax.annotate(name, (x, y), xytext=(3, 3), textcoords="offset points", fontsize=mpl.rcParams["font.size"] - 1,
                        color=st["color"] if name == ours else "#333333")
        xs.append(x)
        ys.append(y)
    if pareto and xs:
        pts = sorted(zip(xs, ys), key=lambda t: (t[0], -t[1]))
        front, best = [], -math.inf
        hi_good = "upper" in better
        for x, y in (pts if "left" in better else pts[::-1]):
            val = y if hi_good else -y
            if val > best:
                front.append((x, y))
                best = val
        fx, fy = zip(*sorted(front))
        ax.plot(fx, fy, color="#999999", linestyle=":", linewidth=0.8, zorder=1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    vert, horiz = better.split()
    ax.annotate("Better", xy=(0.06 if horiz == "left" else 0.94, 0.92 if vert == "upper" else 0.08),
                xytext=(0.24 if horiz == "left" else 0.76, 0.74 if vert == "upper" else 0.26), xycoords="axes fraction",
                ha="center", va="center", fontsize=mpl.rcParams["font.size"] - 1,
                arrowprops=dict(arrowstyle="-|>", color="#555555", linewidth=0.8))
    ax.grid(True, axis="both")
    return ax


def box(ax, data: Dict[str, Sequence[float]], ours: Optional[str] = None, ylabel: str = "", violin: bool = False,
        show_points: bool = False):
    names = list(data)
    vals = [np.asarray(data[n], dtype=float) for n in names]
    if violin:
        parts = ax.violinplot(vals, showmedians=True, widths=0.7)
        for i, b in enumerate(parts["bodies"]):
            st = series_style(names[i], ours)
            b.set_facecolor(st["color"])
            b.set_alpha(0.35)
            b.set_edgecolor("#333333")
    else:
        bp = ax.boxplot(vals, widths=0.55, patch_artist=True, showfliers=not show_points,
                        medianprops=dict(color="#111111", linewidth=1.0), flierprops=dict(markersize=2, alpha=0.5))
        for i, b in enumerate(bp["boxes"]):
            st = series_style(names[i], ours)
            b.set_facecolor(st["color"])
            b.set_alpha(0.55 if names[i] != ours else 0.85)
            b.set_linewidth(0.6)
    if show_points:
        for i, v in enumerate(vals, start=1):
            ax.scatter(i + np.linspace(-0.12, 0.12, v.size), v, s=3, color="#333333", alpha=0.5, zorder=4, linewidth=0)
    ax.set_xticks(range(1, len(names) + 1), labels=names)
    ax.set_ylabel(ylabel)
    return ax


def legend_top(ax_or_fig, ncol: Optional[int] = None, handles=None, labels=None, y: float = 1.02):
    """Single-row frameless legend above the axes (keeps the data area clean)."""
    if handles is None:
        src = ax_or_fig.axes[0] if hasattr(ax_or_fig, "axes") and isinstance(ax_or_fig.axes, list) else ax_or_fig
        handles, labels = src.get_legend_handles_labels()
    ncol = ncol or len(labels)
    if hasattr(ax_or_fig, "legend") and hasattr(ax_or_fig, "savefig"):
        return ax_or_fig.legend(handles, labels, loc="outside upper center", ncol=ncol)
    return ax_or_fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, y), ncol=ncol)


def panel_label(ax, text: str, x: float = -0.02, y: float = 1.02):
    ax.text(x, y, text, transform=ax.transAxes, ha="right", va="bottom", fontweight="bold")


# ----------------------------------------------------------------------------------------------
# Lint + export
# ----------------------------------------------------------------------------------------------
def lint(fig, min_pt: float = MIN_TEXT_PT, warn_pt: float = WARN_TEXT_PT, max_colors: int = 8) -> list:
    """Return a list of human-readable issues found at the printed size."""
    issues = []
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    fbox = fig.bbox
    skip = set()
    for ax in fig.axes:  # tick labels outside the view limits are never drawn
        for axis, lim in ((ax.xaxis, ax.get_xlim()), (ax.yaxis, ax.get_ylim())):
            lo, hi = min(lim), max(lim)
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                loc = tick.get_loc()
                if loc is None or not (lo - 1e-9 * (abs(lo) + 1) <= loc <= hi + 1e-9 * (abs(hi) + 1)):
                    skip.add(id(tick.label1))
                    skip.add(id(tick.label2))
    texts = [t for t in fig.findobj(mpl.text.Text) if t.get_visible() and t.get_text().strip() and id(t) not in skip]
    boxes = []
    for t in texts:
        size = t.get_fontsize()
        label = t.get_text().strip()[:30]
        if size < min_pt:
            issues.append(f"ERROR text '{label}' is {size:.1f} pt (< {min_pt} pt printed)")
        elif size < warn_pt:
            issues.append(f"WARN  text '{label}' is {size:.1f} pt (< {warn_pt} pt recommended)")
        try:
            bb = t.get_window_extent(r)
        except Exception:
            continue
        if bb.x0 < fbox.x0 - 1 or bb.x1 > fbox.x1 + 1 or bb.y0 < fbox.y0 - 1 or bb.y1 > fbox.y1 + 1:
            issues.append(f"WARN  text '{label}' extends outside the figure (clipped in print)")
        boxes.append((label, bb))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            ov_w = min(a.x1, b.x1) - max(a.x0, b.x0)
            ov_h = min(a.y1, b.y1) - max(a.y0, b.y0)
            if ov_w > 1.5 and ov_h > 1.5:
                issues.append(f"ERROR labels overlap: '{boxes[i][0]}' x '{boxes[j][0]}'")
    colors = set()
    for ln in fig.findobj(mpl.lines.Line2D):
        if ln.get_visible() and len(ln.get_xdata()) > 1:
            colors.add(mpl.colors.to_hex(ln.get_color()))
    for p in fig.findobj(mpl.patches.Rectangle):
        if p.get_visible() and p.get_width() > 0 and p.get_facecolor()[3] > 0:
            colors.add(mpl.colors.to_hex(p.get_facecolor()))
    colors -= {"#ffffff", "#000000", "#d9d9d9", "#333333", "#222222"}
    if len(colors) > max_colors:
        issues.append(f"WARN  {len(colors)} distinct colours; readers cannot hold more than ~{max_colors} -- group or facet")
    for ax in fig.axes:
        if ax.get_title():
            issues.append(f"INFO  axes title '{ax.get_title()[:30]}' -- top-venue figures usually put this in the caption instead")
        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            lb = leg.get_window_extent(r)
            covered = 0
            for ln in ax.get_lines():
                xy = ax.transData.transform(np.column_stack([ln.get_xdata(), ln.get_ydata()]).astype(float))
                covered += int(np.sum((xy[:, 0] > lb.x0) & (xy[:, 0] < lb.x1) & (xy[:, 1] > lb.y0) & (xy[:, 1] < lb.y1)))
            if covered:
                issues.append(f"WARN  legend covers {covered} data points -- use legend_top() or a free corner")
    info = getattr(fig, "_paperplot", {})
    w, h = fig.get_size_inches()
    if info and abs(w - info.get("width_in", w)) > 0.05:
        issues.append(f"WARN  figure width {w:.2f}in differs from planned {info['width_in']:.2f}in (text will be rescaled)")
    return issues


def save(fig, path_stem: str, formats: Iterable[str] = ("pdf", "png"), quiet: bool = False) -> list:
    """Save vector PDF (fonts embedded as TrueType) + PNG preview, then print the lint report."""
    os.makedirs(os.path.dirname(os.path.abspath(path_stem)), exist_ok=True)
    issues = lint(fig)
    for f in formats:
        fig.savefig(f"{path_stem}.{f}", dpi=600 if f in ("png", "jpg", "tiff") else None)
    if not quiet:
        print(f"[paperplot] saved {path_stem}.{{{','.join(formats)}}}  size={fig.get_size_inches()[0]:.2f}x{fig.get_size_inches()[1]:.2f}in")
        for i in issues:
            print("  ", i)
        if not issues:
            print("   lint: clean")
    return issues


