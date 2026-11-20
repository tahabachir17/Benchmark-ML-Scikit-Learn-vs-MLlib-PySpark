"""Generates the report figures (vector PDF) and chiffres.tex (numbers quoted in the text).

    python report/make_figures.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "report" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

local = pd.read_csv(ROOT / "results" / "benchmark_results.csv")
cluster = pd.read_csv(ROOT / "results" / "cluster" / "benchmark_results.csv")
SCALES = sorted(local.scale.unique())
CSCALES = sorted(cluster.scale.unique())
PARTS = [2, 8, 16, 32]
SMAX, CMAX = max(SCALES), max(CSCALES)

SK, SP, CL, GRAY = "#d95f02", "#1f6fb2", "#1b9e77", "#8a8a85"
RAMP = ["#a6c8ec", "#5f9fdc", "#1f6fb2", "#0d3f6e"]
NAME = {"lr": "Régression linéaire", "rf": "Random Forest"}

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Latin Modern Roman", "CMU Serif", "DejaVu Serif"],
    "mathtext.fontset": "cm", "font.size": 9, "axes.titlesize": 9.5, "axes.labelsize": 9,
    "legend.fontsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": "#e3e3e0", "grid.linewidth": 0.6, "axes.edgecolor": "#9a9a96",
    "lines.linewidth": 1.8, "lines.markersize": 4.5, "legend.frameon": False,
    "savefig.bbox": "tight", "pdf.fonttype": 42,
})


def sk(df, m, s):
    return df[(df.framework == "sklearn") & (df.model == m) & (df.scale == s)].iloc[0]


def sp(df, m, s, p=None, col="fit_time_s"):
    g = df[(df.framework == "spark") & (df.model == m) & (df.scale == s)]
    if p is not None:
        return g[g.partitions == p].iloc[0]
    return g.loc[g[col].idxmin()]


def rows(df, s):
    return int(sk(df, "lr", s).n_train)


# ------------------------------------------------------------------ figures
def fig_fit_vs_volume():
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.35))
    x = [rows(local, s) for s in SCALES]
    for ax, m in zip(axes, ("lr", "rf")):
        ax.plot(x, [sk(local, m, s).fit_time_s for s in SCALES], "o-", color=SK, label="scikit-learn")
        for p, c in zip(PARTS, RAMP):
            ax.plot(x, [sp(local, m, s, p).fit_time_s for s in SCALES], "s-", color=c, lw=1.2,
                    markersize=3, label=f"Spark, {p} partitions")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_title(NAME[m]); ax.set_xlabel("Lignes d'entraînement")
    axes[0].set_ylabel("Temps d'entraînement (s)")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.17), fontsize=7.5)
    fig.savefig(FIG / "fit_vs_volume.pdf")


def fig_ratio():
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.3), sharey=True)
    x = [rows(local, s) for s in SCALES]
    for ax, col, title in zip(axes, ("fit_time_s", "total_time_s"),
                              ("Entraînement seul", "Temps total (lecture, préparation, fit, prédiction)")):
        for m, c, mk in (("lr", SP, "o"), ("rf", CL, "s")):
            r = [sp(local, m, s, col=col)[col] / sk(local, m, s)[col] for s in SCALES]
            ax.plot(x, r, mk + "-", color=c, label=NAME[m])
        ax.axhline(1, color=GRAY, ls="--", lw=1)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_title(title, fontsize=9)
        ax.set_xlabel("Lignes d'entraînement")
    axes[0].set_ylabel("Temps Spark / temps scikit-learn")
    axes[0].text(1.2e3, 1.12, "égalité", color=GRAY, fontsize=7.5)
    axes[0].legend(loc="upper right")
    fig.savefig(FIG / "ratio_basculement.pdf")


def fig_partitions():
    fig, axes = plt.subplots(2, 2, figsize=(6.3, 3.9))
    for i, s in enumerate((1, SMAX)):
        for j, m in enumerate(("lr", "rf")):
            ax = axes[i][j]
            vals = [sp(local, m, s, p).fit_time_s for p in PARTS]
            bars = ax.bar([str(p) for p in PARTS], vals, color=RAMP, width=0.62)
            ax.axhline(sk(local, m, s).fit_time_s, color=SK, ls="--", lw=1.4, label="scikit-learn")
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}".replace(".", ","), ha="center",
                        va="bottom", fontsize=7.5)
            ax.set_title(f"{NAME[m]}, x{s} ({rows(local, s):,} lignes)".replace(",", " "))
            ax.grid(axis="x", visible=False)
            ax.set_ylim(0, max(vals + [sk(local, m, s).fit_time_s]) * 1.22)
            if j == 0:
                ax.set_ylabel("Temps d'entraînement (s)")
            if i == 1:
                ax.set_xlabel("Nombre de partitions")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.legend(*axes[0][0].get_legend_handles_labels(), loc="upper center", ncol=1, fontsize=8,
               bbox_to_anchor=(0.5, 1.0))
    fig.savefig(FIG / "partitions.pdf")


def fig_shuffle_memory():
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.35))
    ax = axes[0]
    w = 0.38
    xs = range(len(PARTS))
    for k, (m, c) in enumerate((("lr", "#9cc2ee"), ("rf", SP))):
        ax.bar([i + (k - 0.5) * w for i in xs], [sp(local, m, SMAX, p).shuffle_write_mb for p in PARTS],
               width=w, color=c, label=NAME[m])
    ax.set_xticks(list(xs), [str(p) for p in PARTS])
    ax.set_xlabel("Nombre de partitions"); ax.set_ylabel("Shuffle écrit par exécution (Mo)")
    ax.set_title(f"Volume de shuffle, x{SMAX}"); ax.grid(axis="x", visible=False)
    ax.set_ylim(0, 205); ax.legend(loc="upper left", ncol=2, fontsize=7.5)
    ax = axes[1]
    x = [rows(local, s) for s in SCALES]
    ax.plot(x, [sk(local, "rf", s).peak_mem_mb / 1024 for s in SCALES], "o-", color=SK, label="scikit-learn")
    ax.plot(x, [local[(local.framework == "spark") & (local.model == "rf") & (local.scale == s)].peak_mem_mb.max() / 1024
                for s in SCALES], "s-", color=SP, label="Spark (pilote + JVM)")
    ax.set_xscale("log"); ax.set_xlabel("Lignes d'entraînement"); ax.set_ylabel("Pic de mémoire (Go)")
    ax.set_title("Mémoire, Random Forest"); ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "shuffle_memoire.pdf")


def fig_cluster():
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.3))
    x = [rows(cluster, s) for s in CSCALES]
    for ax, m in zip(axes, ("lr", "rf")):
        ax.plot(x, [sk(local, m, s).fit_time_s for s in CSCALES], "o-", color=SK, label="scikit-learn (hôte, 8 cœurs)")
        ax.plot(x, [sk(cluster, m, s).fit_time_s for s in CSCALES], "o--", color=SK, alpha=0.75,
                label="scikit-learn (conteneur, 4 cœurs)")
        ax.plot(x, [sp(local, m, s).fit_time_s for s in CSCALES], "s-", color=SP, label="Spark local[*]")
        ax.plot(x, [sp(cluster, m, s).fit_time_s for s in CSCALES], "^-", color=CL, label="Spark standalone")
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_title(NAME[m]); ax.set_xlabel("Lignes d'entraînement")
    axes[0].set_ylabel("Temps d'entraînement (s)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=4, fontsize=7.5,
               bbox_to_anchor=(0.5, -0.17))
    fig.savefig(FIG / "local_vs_cluster.pdf")


# ------------------------------------------------------------------ numbers for the text
def fr(x, d=2):
    return f"{x:,.{d}f}".replace(",", "\\,").replace(".", "{,}")


def write_numbers():
    N = {}
    N["nMaxTrain"] = fr(rows(local, SMAX), 0)
    N["nMilleTrain"] = fr(rows(local, 1000), 0)
    N["nUnTrain"] = fr(rows(local, 1), 0)
    N["scaleMax"] = str(SMAX)
    for m, M in (("lr", "LR"), ("rf", "RF")):
        a, b = sk(local, m, SMAX), sp(local, m, SMAX)
        N[f"skFit{M}Max"] = fr(a.fit_time_s); N[f"spFit{M}Max"] = fr(b.fit_time_s)
        N[f"gain{M}Max"] = fr(a.fit_time_s / b.fit_time_s)
        N[f"ratio{M}Mille"] = fr(sp(local, m, 1000).fit_time_s / sk(local, m, 1000).fit_time_s)
        tsk = a.total_time_s
        tsp = local[(local.framework == "spark") & (local.model == m) & (local.scale == SMAX)].total_time_s.min()
        N[f"skTot{M}Max"] = fr(tsk); N[f"spTot{M}Max"] = fr(tsp); N[f"ratioTot{M}Max"] = fr(tsp / tsk)
        N[f"skFit{M}Un"] = fr(sk(local, m, 1).fit_time_s, 3); N[f"spFit{M}Un"] = fr(sp(local, m, 1).fit_time_s)
        N[f"ratio{M}Un"] = fr(sp(local, m, 1).fit_time_s / sk(local, m, 1).fit_time_s, 0)
        for p, word in zip(PARTS, ("Deux", "Huit", "Seize", "TrenteDeux")):
            N[f"spFit{M}MaxP{word}"] = fr(sp(local, m, SMAX, p).fit_time_s)
        N[f"rdeux{M}sk"] = fr(a.r2, 4); N[f"rdeux{M}sp"] = fr(b.r2, 4)
        N[f"rmse{M}sk"] = fr(a.rmse, 0); N[f"rmse{M}sp"] = fr(b.rmse, 0)
        N[f"mae{M}sk"] = fr(a.mae, 0); N[f"mae{M}sp"] = fr(b.mae, 0)
        N[f"rdeux{M}skUn"] = fr(sk(local, m, 1).r2, 4); N[f"rdeux{M}spUn"] = fr(sp(local, m, 1).r2, 4)
        N[f"rmse{M}skUn"] = fr(sk(local, m, 1).rmse, 0); N[f"rmse{M}spUn"] = fr(sp(local, m, 1).rmse, 0)
        c_sk, c_l, c_c = sk(cluster, m, CMAX), sp(local, m, CMAX), sp(cluster, m, CMAX)
        N[f"cSk{M}"] = fr(c_sk.fit_time_s); N[f"cLocal{M}"] = fr(c_l.fit_time_s); N[f"cClu{M}"] = fr(c_c.fit_time_s)
        N[f"cCluSk{M}"] = fr(c_c.fit_time_s / c_sk.fit_time_s); N[f"cCluLocal{M}"] = fr(c_c.fit_time_s / c_l.fit_time_s)
        N[f"cCluLocalPct{M}"] = fr((c_c.fit_time_s / c_l.fit_time_s - 1) * 100, 0)
        N[f"shufUn{M}PDeux"] = fr(sp(local, m, 1, 2).shuffle_write_mb)
        N[f"shufUn{M}PTrenteDeux"] = fr(sp(local, m, 1, 32).shuffle_write_mb)
        N[f"shufMax{M}PDeux"] = fr(sp(local, m, SMAX, 2).shuffle_write_mb, 1)
        N[f"shufMax{M}PTrenteDeux"] = fr(sp(local, m, SMAX, 32).shuffle_write_mb, 1)
    small = local[(local.framework == "spark") & (local.scale == 1)].groupby("partitions").fit_time_s.mean()
    N["slowdownSmall"] = fr((small[32] / small[2] - 1) * 100, 0)
    N["memSkRFMax"] = fr(sk(local, "rf", SMAX).peak_mem_mb / 1024, 1)
    N["memSpRFMax"] = fr(local[(local.framework == "spark") & (local.model == "rf") & (local.scale == SMAX)].peak_mem_mb.max() / 1024, 1)
    N["memSpMinUn"] = fr(local[(local.framework == "spark") & (local.scale == 1)].peak_mem_mb.min() / 1024, 1)
    N["scaleCluMax"] = str(CMAX)
    N["nCluMaxTrain"] = fr(rows(cluster, CMAX), 0)
    N["nRunsSpark"] = str(len(local[local.framework == "spark"]))
    lines = ["% Fichier généré par make_figures.py à partir des résultats du benchmark. Ne pas modifier à la main."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in N.items()]
    (ROOT / "report" / "chiffres.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tables():
    """Booktabs bodies included by main.tex."""
    out = []
    for s in SCALES:
        cells = [f"x{s}", fr(rows(local, s), 0)]
        for m in ("lr", "rf"):
            a, b = sk(local, m, s), sp(local, m, s)
            ratio = b.fit_time_s / a.fit_time_s
            r = fr(ratio)
            cells += [fr(a.fit_time_s, 3), f"{fr(b.fit_time_s)} ({int(b.partitions)})",
                      f"\\textbf{{{r}}}" if ratio < 1 else r]
        out.append(" & ".join(cells) + r" \\")
    (ROOT / "report" / "table_fit.tex").write_text("\n".join(out) + "\n", encoding="utf-8")

    out = []
    for m in ("lr", "rf"):
        for s in CSCALES:
            c_sk, c_l, c_c = sk(cluster, m, s), sp(local, m, s), sp(cluster, m, s)
            out.append(" & ".join([{"lr": "Rég. linéaire", "rf": "Random Forest"}[m] if s == CSCALES[0] else "", f"x{s}", fr(c_sk.fit_time_s),
                                   f"{fr(c_l.fit_time_s)} ({int(c_l.partitions)})",
                                   f"{fr(c_c.fit_time_s)} ({int(c_c.partitions)})",
                                   fr(c_c.fit_time_s / c_sk.fit_time_s), fr(c_c.fit_time_s / c_l.fit_time_s)]) + r" \\")
        if m == "lr":
            out.append(r"\midrule")
    (ROOT / "report" / "table_cluster.tex").write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    fig_fit_vs_volume(); fig_ratio(); fig_partitions(); fig_shuffle_memory(); fig_cluster()
    write_numbers(); write_tables()
    print("figures + chiffres.tex OK")
