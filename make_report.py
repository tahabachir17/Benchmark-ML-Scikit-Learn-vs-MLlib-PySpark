"""Builds benchmark_report.pdf from results/benchmark_results.csv (matplotlib only).

    python make_report.py
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from common import RESULTS_DIR, ROOT

# ----------------------------------------------------------------- palette
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SKLEARN = "#eb6834"                                   # categorical slot 2 (orange)
SPARK_RAMP = ["#a9cbf2", "#6aa5ea", "#2a78d6", "#1a4f94", "#0f3060"]  # blue, light -> dark
GREEN, GREEN_LIGHT, GREEN_ROW = "#1e7b3c", "#dff5e6", "#f1f8f3"
MODEL_NAME = {"lr": "Régression Linéaire", "rf": "Random Forest"}

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 7.5, "axes.titlesize": 8.5, "axes.titlecolor": INK, "legend.frameon": False,
    "lines.linewidth": 2, "lines.markersize": 5, "pdf.fonttype": 42,
})

# A4 portrait, inches
W, H, M = 8.27, 11.69, 0.7


def fmt_int(x) -> str:
    return f"{x:,.0f}".replace(",", " ")


def spark_color(p, parts):
    return SPARK_RAMP[min(sorted(parts).index(p), len(SPARK_RAMP) - 1)]


# ----------------------------------------------------------------- page layout
class Doc:
    """Minimal flowing layout on top of matplotlib figures (one figure per page)."""

    def __init__(self, pdf: PdfPages, footer: str):
        self.pdf, self.footer, self.page, self.fig = pdf, footer, 0, None
        self.new_page()

    def new_page(self):
        if self.fig is not None:
            self._finish()
        self.page += 1
        self.fig = plt.figure(figsize=(W, H))
        self.y = H - M

    def _finish(self):
        self.fig.text(M / W, 0.4 / H, self.footer, fontsize=6.5, color=INK2)
        self.fig.text(1 - M / W, 0.4 / H, f"Page {self.page}", fontsize=6.5, color=INK2,
                      ha="right")
        self.pdf.savefig(self.fig)
        plt.close(self.fig)

    def close(self):
        self._finish()

    def need(self, h):
        if self.y - h < M:
            self.new_page()

    def space(self, h):
        self.y -= h

    def banner(self, kicker, title, subtitle):
        h = 1.05
        ax = self.fig.add_axes([M / W, (self.y - h) / H, (W - 2 * M) / W, h / H])
        ax.set_facecolor(GREEN); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.text(0.03, 0.78, kicker, color="#c8f0d4", fontsize=7, weight="bold", transform=ax.transAxes)
        ax.text(0.03, 0.45, title, color="white", fontsize=17, weight="bold", transform=ax.transAxes)
        ax.text(0.03, 0.16, subtitle, color=GREEN_LIGHT, fontsize=8.5, transform=ax.transAxes)
        self.y -= h + 0.2

    def heading(self, s, keep=0.6):
        """`keep`: height (in) of what follows, so a heading never ends a page alone."""
        self.need(0.36 + keep)
        self.fig.text(M / W, (self.y - 0.2) / H, s, fontsize=11.5, weight="bold", color=GREEN)
        self.y -= 0.36

    def para(self, s, size=8.5, color=INK, indent=0.0, bold=False, bullet=False):
        usable = W - 2 * M - indent - (0.15 if bullet else 0)
        chars = int(usable * 72 / (size * 0.56))
        lines = textwrap.wrap(s, chars) or [""]
        lh = size * 1.45 / 72
        self.need(lh * len(lines))
        x = M + indent
        for i, line in enumerate(lines):
            self.y -= lh
            if bullet and i == 0:
                self.fig.text(x / W, self.y / H, "•", fontsize=size, color=GREEN)
            self.fig.text((x + (0.15 if bullet else 0)) / W, self.y / H, line, fontsize=size,
                          color=color, weight="bold" if bold else "normal")
        self.y -= lh * 0.35

    def table(self, rows, col_widths, size=7, row_h=0.22, align_first="left", align="right"):
        header, body = rows[0], rows[1:]
        while body:
            self.need(row_h * 3)
            fit = max(1, int((self.y - M) / row_h) - 1)
            chunk, body = body[:fit], body[fit:]
            h = row_h * (len(chunk) + 1)
            total = sum(col_widths)
            ax = self.fig.add_axes([M / W, (self.y - h) / H, (W - 2 * M) / W, h / H])
            ax.axis("off")
            t = ax.table(cellText=chunk, colLabels=header, bbox=[0, 0, 1, 1],
                         colWidths=[c / total for c in col_widths], cellLoc=align)
            t.auto_set_font_size(False)
            for (r, c), cell in t.get_celld().items():
                cell.set_fontsize(size)
                cell.set_edgecolor("#c9d8cd"); cell.set_linewidth(0.4)
                if r == 0:
                    cell.set_facecolor(GREEN)
                    cell.get_text().set_color("white"); cell.get_text().set_weight("bold")
                    cell.get_text().set_ha("center")
                else:
                    cell.set_facecolor("white" if r % 2 else GREEN_ROW)
                    if c == 0:
                        cell.get_text().set_ha(align_first)
            self.y -= h + 0.12

    def charts(self, n, h, draw):
        """Row of `n` chart axes, height `h` inches; draw(list_of_axes)."""
        self.need(h)
        gap, left_pad, bottom_pad, top_pad = 0.35, 0.55, 0.42, 0.28
        cw = (W - 2 * M - gap * (n - 1)) / n
        axes = []
        for i in range(n):
            x0 = M + i * (cw + gap) + left_pad
            axes.append(self.fig.add_axes([x0 / W, (self.y - h + bottom_pad) / H,
                                           (cw - left_pad) / W, (h - bottom_pad - top_pad) / H]))
        draw(axes)
        self.y -= h + 0.05


# ----------------------------------------------------------------- charts
def draw_fit_vs_rows(df, models, parts):
    def draw(axes):
        for ax, m in zip(axes, models):
            sk = df[(df.framework == "sklearn") & (df.model == m)].sort_values("n_train")
            ax.plot(sk.n_train, sk.fit_time_s, "o-", color=SKLEARN, label="scikit-learn")
            for p in parts:
                sp = df[(df.framework == "spark") & (df.model == m) & (df.partitions == p)]
                sp = sp.sort_values("n_train")
                ax.plot(sp.n_train, sp.fit_time_s, "s-", color=spark_color(p, parts),
                        label=f"Spark p={p}", markersize=4)
            ax.set_xscale("log"); ax.set_yscale("log")
            ax.set_title(MODEL_NAME[m]); ax.set_xlabel("Lignes d'entraînement")
            ax.set_ylabel("Temps d'entraînement (s)")
        axes[0].legend(fontsize=6.5)
    return draw


def draw_vs_partitions(df, models, parts, scale, col, ylabel, sklearn_line=True):
    def draw(axes):
        for ax, m in zip(axes, models):
            sp = df[(df.framework == "spark") & (df.model == m) & (df.scale == scale)]
            sp = sp.sort_values("partitions")
            ax.bar([str(p) for p in sp.partitions], sp[col], width=0.6,
                   color=[spark_color(p, parts) for p in sp.partitions], label="Spark MLlib")
            if sklearn_line:
                sk = df[(df.framework == "sklearn") & (df.model == m) & (df.scale == scale)]
                if len(sk):
                    ax.axhline(sk[col].iloc[0], color=SKLEARN, lw=2, ls="--", label="scikit-learn")
            ax.set_title(f"{MODEL_NAME[m]} (x{scale})")
            ax.set_xlabel("Nombre de partitions"); ax.set_ylabel(ylabel)
            ax.grid(axis="x", visible=False)
        if sklearn_line:
            axes[0].legend(fontsize=6.5)
    return draw


def draw_memory(df, models):
    def draw(axes):
        for ax, m in zip(axes, models):
            sk = df[(df.framework == "sklearn") & (df.model == m)].sort_values("n_train")
            ax.plot(sk.n_train, sk.peak_mem_mb, "o-", color=SKLEARN, label="scikit-learn (Python)")
            sp = (df[(df.framework == "spark") & (df.model == m)]
                  .groupby("n_train", as_index=False).peak_mem_mb.max())
            ax.plot(sp.n_train, sp.peak_mem_mb, "s-", color=SPARK_RAMP[2],
                    label="Spark (driver Python + JVM)")
            ax.set_xscale("log"); ax.set_title(MODEL_NAME[m])
            ax.set_xlabel("Lignes d'entraînement"); ax.set_ylabel("Pic RSS (MB)")
        axes[0].legend(fontsize=6.5)
    return draw


# ----------------------------------------------------------------- analysis
def summary_table(df):
    """Per (scale, model): sklearn fit, best Spark fit + partitions, ratio, R2."""
    rows = []
    for (s, m), g in df.groupby(["scale", "model"]):
        sk, sp = g[g.framework == "sklearn"], g[g.framework == "spark"]
        if sk.empty or sp.empty:
            continue
        best, sk = sp.loc[sp.fit_time_s.idxmin()], sk.iloc[0]
        rows.append({
            "scale": s, "model": m, "n_train": int(sk.n_train),
            "sk_fit": sk.fit_time_s, "sp_fit": best.fit_time_s, "best_p": int(best.partitions),
            "ratio": best.fit_time_s / sk.fit_time_s,
            "sk_r2": sk.r2, "sp_r2": best.r2, "sk_rmse": sk.rmse, "sp_rmse": best.rmse,
        })
    return pd.DataFrame(rows).sort_values(["model", "scale"])


def analysis(summ, df):
    """List of (bold title, body) findings."""
    out = []
    for m, g in summ.groupby("model"):
        g = g.sort_values("scale")
        wins = g[g.ratio < 1]
        name = MODEL_NAME[m]
        if len(wins):
            f = wins.iloc[0]
            body = (f"premier volume testé où le fit Spark est plus rapide que scikit-learn : ~"
                    f"{fmt_int(f.n_train)} lignes d'entraînement (x{f.scale}), avec "
                    f"{f.best_p} partitions ({f.sp_fit:.2f}s contre {f.sk_fit:.2f}s, "
                    f"soit {1 / f.ratio:.1f}x plus rapide).")
            g_s = df[(df.model == m) & (df.scale == f.scale)]
            sk_tot = g_s[g_s.framework == "sklearn"].total_time_s.iloc[0]
            sp_tot = g_s[g_s.framework == "spark"].total_time_s.min()
            if sp_tot < sk_tot:
                body += (f" En temps total (lecture + préparation + fit + prédiction), Spark est "
                         f"aussi plus rapide ({sp_tot:.2f}s contre {sk_tot:.2f}s).")
            else:
                body += (f" En temps total (lecture + préparation + fit + prédiction), Spark reste "
                         f"{sp_tot / sk_tot:.2f}x plus lent ({sp_tot:.2f}s contre {sk_tot:.2f}s) : "
                         f"le basculement n'est atteint que sur l'entraînement.")
            out.append((name, body))
            continue
        last = g.iloc[-1]
        body = (f"aucun basculement dans la plage testée. Au plus grand volume "
                f"({fmt_int(last.n_train)} lignes), Spark reste {last.ratio:.1f}x plus lent "
                f"({last.sp_fit:.2f}s avec p={last.best_p} contre {last.sk_fit:.2f}s).")
        out.append((name, body))

    for s, label in ((df.scale.min(), "petit volume"), (df.scale.max(), "grand volume")):
        sp = df[(df.framework == "spark") & (df.scale == s)]
        if sp.empty:
            continue
        by_p = sp.groupby("partitions").agg(fit=("fit_time_s", "mean"),
                                            sh=("shuffle_write_mb", "mean"))
        pmin, pmax = by_p.index.min(), by_p.index.max()
        delta = (by_p.fit[pmax] / by_p.fit[pmin] - 1) * 100
        out.append((f"Effet des partitions ({label}, x{s})",
                    f"passer de {pmin} à {pmax} partitions "
                    f"{'ralentit' if delta > 0 else 'accélère'} l'entraînement de {abs(delta):.0f}% "
                    f"en moyenne ; shuffle écrit {by_p.sh[pmin]:.2f} MB -> {by_p.sh[pmax]:.2f} MB. "
                    f"Meilleur choix : p={by_p.fit.idxmin()}."))
    return out


# ----------------------------------------------------------------- local vs cluster
CLUSTER_COLOR = "#1baf7a"   # categorical slot 3 (aqua); slots 1-3 validate all-pairs


def best_spark(df, col="fit_time_s"):
    """Fastest Spark run per (model, scale)."""
    sp = df[df.framework == "spark"]
    return sp.loc[sp.groupby(["model", "scale"])[col].idxmin()].set_index(["model", "scale"])


def draw_local_vs_cluster(local, cluster, models):
    def draw(axes):
        common = sorted(set(local.scale) & set(cluster.scale))
        for ax, m in zip(axes, models):
            for d, sk_style, sp_color, label in ((local, "-", SPARK_RAMP[2], "local[*]"),
                                                 (cluster, "--", CLUSTER_COLOR, "cluster Docker")):
                d = d[(d.model == m) & (d.scale.isin(common))]
                sk = d[d.framework == "sklearn"].sort_values("n_train")
                sp = best_spark(d).loc[m].sort_values("n_train")
                ax.plot(sk.n_train, sk.fit_time_s, "o" + sk_style, color=SKLEARN,
                        label=f"scikit-learn ({'local' if label == 'local[*]' else 'Docker'})")
                ax.plot(sp.n_train, sp.fit_time_s, "s-", color=sp_color,
                        label=f"Spark {label} (meilleur p)", markersize=4)
            ax.set_xscale("log"); ax.set_yscale("log"); ax.set_title(MODEL_NAME[m])
            ax.set_xlabel("Lignes d'entraînement"); ax.set_ylabel("Temps d'entraînement (s)")
        axes[-1].legend(fontsize=6, loc="upper left")  # RF panel: empty top-left corner
    return draw


def add_cluster_section(doc, local, cluster_csv, models, usable, local_env):
    cluster = pd.read_csv(cluster_csv)
    env_file = cluster_csv.parent / "environment.json"
    cenv = json.loads(env_file.read_text()) if env_file.exists() else {}
    topo_file = cluster_csv.parent / "cluster_topology.json"
    topo = json.loads(topo_file.read_text()) if topo_file.exists() else {}
    workers = topo.get("workers", [])
    common = sorted(set(local.scale) & set(cluster.scale))

    doc.new_page()
    doc.heading("9. Mono-nœud vs cluster Spark (standalone, 2 workers)")
    worker_txt = (", ".join(f"{w['host']} ({w['cores']} cœurs, {w['memory']} MB)" for w in workers)
                  if workers else "voir cluster_topology.json")
    doc.table([
        ["Paramètre", "Valeur"],
        ["Master", cenv.get("master", "?")],
        ["Workers", f"{topo.get('aliveworkers', '?')} vivants : {worker_txt}"],
        ["Cœurs exécuteurs", f"{topo.get('cores', '?')} au total (local[*] : {local_env.get('logical_cores', '?')} cœurs)"],
        ["scikit-learn (même conteneur)", f"{cenv.get('sklearn_version', '?')} - n_jobs={cenv.get('sklearn_n_jobs', '?')}, "
                                          f"Python {cenv.get('python', '?')}"],
        ["Volumes", ", ".join(f"x{s}" for s in sorted(cluster.scale.unique()))],
        ["Répétitions", f"{cenv.get('repeats', '?')} (médiane) - {cenv.get('date', '')}"],
    ], [1.9, usable - 1.9], size=7.5, align="left")
    doc.para("Ce cluster est un vrai ordonnanceur Spark standalone (master + 2 workers, exécuteurs "
             "séparés), mais les conteneurs partagent une seule machine physique : il démontre la "
             "distribution des tâches, pas le coût réseau entre machines. Dans le cluster, "
             "scikit-learn tourne dans le conteneur pilote avec 4 threads, pour une comparaison à "
             "ressources égales (4 cœurs de chaque côté).", size=7.5)

    lb, cb = best_spark(local), best_spark(cluster)
    rows, findings = [], []
    for m in models:
        first_win = None
        for s in sorted(cluster.scale.unique()):
            csk = cluster[(cluster.framework == "sklearn") & (cluster.model == m) & (cluster.scale == s)].iloc[0]
            c = cb.loc[(m, s)]
            if first_win is None and c.fit_time_s < csk.fit_time_s:
                first_win = (s, c, csk)
            if s not in common:
                continue
            lsk = local[(local.framework == "sklearn") & (local.model == m) & (local.scale == s)].iloc[0]
            l = lb.loc[(m, s)]
            rows.append([m.upper(), f"x{s}", f"{lsk.fit_time_s:.2f}", f"{l.fit_time_s:.2f} (p={int(l.partitions)})",
                         f"{csk.fit_time_s:.2f}", f"{c.fit_time_s:.2f} (p={int(c.partitions)})",
                         f"{c.fit_time_s / csk.fit_time_s:.2f}x", f"{c.fit_time_s / l.fit_time_s:.2f}x"])
        smax = max(common)
        c, l = cb.loc[(m, smax)], lb.loc[(m, smax)]
        csk = cluster[(cluster.framework == "sklearn") & (cluster.model == m) & (cluster.scale == smax)].iloc[0]
        if first_win:
            s, cw, skw = first_win
            body = (f"dans le cluster, Spark devient plus rapide que scikit-learn (4 threads) au volume "
                    f"x{s} ({fmt_int(cw.n_train)} lignes) : {cw.fit_time_s:.2f}s contre {skw.fit_time_s:.2f}s.")
        else:
            body = (f"aucun basculement dans le cluster jusqu'à x{max(cluster.scale)} ; à x{smax}, Spark "
                    f"y est {c.fit_time_s / csk.fit_time_s:.1f}x plus lent que scikit-learn "
                    f"({c.fit_time_s:.2f}s contre {csk.fit_time_s:.2f}s).")
        body += (f" À x{smax}, le meilleur fit Spark du cluster est {c.fit_time_s / l.fit_time_s:.2f}x "
                 f"celui de local[*] ({c.fit_time_s:.2f}s contre {l.fit_time_s:.2f}s).")
        findings.append((MODEL_NAME[m], body))

    for title, body in findings:
        doc.para(title, bold=True, bullet=True)
        doc.para(body, indent=0.15)
    doc.charts(len(models), 2.45, draw_local_vs_cluster(local, cluster, models))
    doc.para("Échelles log-log. Bleu : Spark local[*] ; vert : Spark cluster Docker ; orange plein / "
             "pointillé : scikit-learn local / dans le conteneur.", size=7, color=INK2)
    doc.table([["Modèle", "Éch.", "sk local (s)", "Spark local (s)", "sk Docker (s)",
                "Spark cluster (s)", "Cluster/sk", "Cluster/local"]] + rows,
              [0.55, 0.5, 0.8, 1.1, 0.85, 1.15, 0.8, 0.85], size=6.5, row_h=0.19)
    doc.para("Temps de fit, médianes. Cluster/sk = Spark cluster / scikit-learn Docker (même machine "
             "virtuelle, mêmes 4 cœurs) ; Cluster/local = Spark cluster / Spark local[*]. "
             "Les versions Python / scikit-learn diffèrent entre Windows et le conteneur : comparer "
             "les moteurs au sein de chaque environnement.", size=7, color=INK2)


# ----------------------------------------------------------------- PDF
def build_report(csv_path: Path | None = None, out_path: Path | None = None) -> Path:
    csv_path = csv_path or RESULTS_DIR / "benchmark_results.csv"
    out_path = out_path or ROOT / "benchmark_report.pdf"
    df = pd.read_csv(csv_path)
    env_file = csv_path.parent / "environment.json"
    env = json.loads(env_file.read_text()) if env_file.exists() else {}
    models = [m for m in ("lr", "rf") if m in set(df.model)]
    parts = sorted(int(p) for p in df[df.framework == "spark"].partitions.unique())
    smax = int(df.scale.max())
    summ = summary_table(df)
    usable = W - 2 * M

    with PdfPages(out_path) as pdf:
        info = pdf.infodict()
        info["Title"] = "Benchmark ML : Scikit-Learn vs MLlib"
        doc = Doc(pdf, "Mini-projet 08 - Benchmark Scikit-Learn vs PySpark MLlib")
        doc.banner("MINI-PROJET 08", "Benchmark ML : Scikit-Learn vs MLlib",
                   "Rapport de benchmark - PySpark MLlib • Scikit-Learn • Scalabilité • Partitioning")

        doc.heading("1. Objectif & protocole")
        doc.para("Prédire les dépenses de santé individuelles (charges) du jeu de données Insurance "
                 "et comparer une approche mono-nœud (scikit-learn) à une approche distribuée "
                 "(PySpark MLlib) en faisant varier le volume de données et le nombre de partitions. "
                 "Les deux implémentations utilisent le même prétraitement (one-hot de sex, smoker, "
                 "region + age, bmi, children), avec 20 arbres et une profondeur de 5 pour "
                 "les deux Random Forest. Le jeu original (1 338 lignes) est répliqué avec un léger "
                 "bruit gaussien pour simuler des volumes plus importants.")
        doc.table([
            ["Paramètre", "Valeur"],
            ["Volumes testés", ", ".join(f"x{s}" for s in sorted(df.scale.unique()))],
            ["Partitions Spark", ", ".join(map(str, parts))],
            ["Spark", f"{env.get('spark_version', '?')} - master {env.get('master', '?')}"],
            ["Expérience", env.get("run_label", "single-host")],
            ["scikit-learn", f"{env.get('sklearn_version', '?')} - n_jobs={env.get('sklearn_n_jobs', '?')}"],
            ["Machine", f"{env.get('logical_cores', '?')} cœurs logiques, {env.get('ram_gb', '?')} GB RAM, "
                        f"{env.get('os', '')}"],
            ["Répétitions", f"{env.get('repeats', '?')} (médiane retenue) - {env.get('date', '')}"],
        ], [1.9, usable - 1.9], size=7.5, align="left")

        doc.para("Mode mesuré : " + env.get("execution_mode", env.get("master", "inconnu")), bold=True)
        doc.para("Découpage commun par source avant réplication : les copies restent du même côté. "
                 "Les volumes synthétiques mesurent la charge de calcul, pas une population indépendante. "
                 "Aucune extrapolation du seuil hors des volumes mesurés. Les forêts ont 20 arbres et "
                 "profondeur 5 ; les algorithmes et leurs autres paramètres diffèrent.", size=7.5)
        doc.heading("2. Comparaison des temps de fit")
        for title, body in analysis(summ, df):
            doc.para(title, bold=True, bullet=True)
            doc.para(body, indent=0.15)
        doc.para("Interprétation : sur de petits volumes, le coût fixe de Spark (planification des "
                 "jobs, sérialisation JVM, une tâche par partition, échanges shuffle) domine le "
                 "calcul utile ; scikit-learn, qui travaille directement en RAM, est alors nettement "
                 "plus rapide. Quand le volume augmente, le parallélisme de Spark peut amortir ces coûts. "
                 "Trop de partitions pour un petit volume multiplie les tâches et le shuffle sans "
                 "gain de calcul.", color=INK2)

        doc.heading("3. Temps d'entraînement vs volume", keep=2.9)
        doc.charts(len(models), 2.9, draw_fit_vs_rows(df, models, parts))
        doc.para("Échelles log-log. Orange : scikit-learn ; bleus (clair -> foncé) : Spark avec un "
                 "nombre croissant de partitions.", size=7, color=INK2)

        doc.heading("4. Tableau récapitulatif")
        doc.table([["Modèle", "Éch.", "Lignes", "Fit sk (s)", "Fit Sp (s)", "Best p",
                    "Ratio", "R² sk", "R² Spark", "RMSE sk", "RMSE Spark"]] +
                  [[MODEL_NAME[r.model].replace("Régression ", "Rég. "), f"x{r.scale}",
                    fmt_int(r.n_train), f"{r.sk_fit:.3f}", f"{r.sp_fit:.3f}", str(r.best_p),
                    f"{r.ratio:.1f}x", f"{r.sk_r2:.4f}", f"{r.sp_r2:.4f}", fmt_int(r.sk_rmse),
                    fmt_int(r.sp_rmse)] for r in summ.itertuples()],
                  [0.85, 0.5, 0.65, 0.65, 0.6, 0.5, 0.65, 0.55, 0.55, 0.6, 0.6], size=6.5)
        doc.para("Ratio < 1 : Spark plus rapide. R² et RMSE calculés sur un découpage "
                 "commun par source. sk = scikit-learn ; Best p = partitions du meilleur run Spark ; "
                 "Ratio = fit Spark / fit sklearn.", size=7, color=INK2)

        doc.heading(f"5. Impact du nombre de partitions (x{smax})", keep=2.5)
        doc.charts(len(models), 2.5, draw_vs_partitions(df, models, parts, smax, "fit_time_s",
                                                        "Temps d'entraînement (s)"))
        doc.heading("Shuffle selon les partitions", keep=2.5)
        doc.charts(len(models), 2.5, draw_vs_partitions(df, models, parts, smax, "shuffle_write_mb",
                                                        "Shuffle écrit (MB)", sklearn_line=False))
        doc.para("Shuffle mesuré via l'API REST Spark : octets écrits par les stages du run "
                 "(repartition, agrégation des statistiques / histogrammes des arbres).",
                 size=7, color=INK2)

        doc.heading("6. Mémoire consommée", keep=2.5)
        doc.charts(len(models), 2.5, draw_memory(df, models))
        doc.para("RSS du pilote et de ses enfants toutes les 50 ms ; JVM locale incluse. "
                 "Exécuteurs distants exclus : ceci ne mesure pas la mémoire totale du cluster. "
                 "La JVM réutilisée peut retenir la mémoire des essais précédents.",
                 size=7, color=INK2)

        doc.new_page()
        doc.heading("7. Résultats détaillés")
        det = df.sort_values(["model", "scale", "framework", "partitions"])
        doc.table([["Framework", "Modèle", "Éch.", "p", "Fit (s)", "Inf. (s)", "R²", "RMSE",
                    "MAE", "Pic mém. (MB)", "Shuffle W (MB)"]] +
                  [[r.framework, r.model.upper(), f"x{r.scale}", str(r.partitions),
                    f"{r.fit_time_s:.3f}", f"{r.inference_time_s:.3f}", f"{r.r2:.4f}",
                    fmt_int(r.rmse), fmt_int(r.mae), fmt_int(r.peak_mem_mb),
                    f"{r.shuffle_write_mb:.2f}"] for r in det.itertuples()],
                  [0.7, 0.55, 0.5, 0.35, 0.6, 0.6, 0.6, 0.65, 0.6, 0.85, 0.85], size=6.5,
                  row_h=0.18)
        doc.heading("8. Temps complet et variabilité")
        doc.para("Total = lecture / préparation + fit du pipeline + prédiction forcée. "
                 "Démarrage Spark, génération des CSV et calcul des métriques exclus. "
                 "Médianes des répétitions ; écart-type calculé sur les totaux individuels. "
                 "Shuffle : octets du run complet, y compris préparation et évaluation ; "
                 "ces octets ne prouvent pas un coût réseau entre machines.", size=7.5)
        total_rows = []
        for (scale, model), group in df.groupby(["scale", "model"]):
            sk = group[group.framework == "sklearn"].iloc[0]
            sp = group[group.framework == "spark"].sort_values("total_time_s").iloc[0]
            total_rows.append([model.upper(), f"x{scale}", str(int(sp.partitions)),
                               f"{sk.total_time_s:.3f}", f"{sp.total_time_s:.3f}",
                               f"{sp.total_time_s / sk.total_time_s:.2f}x",
                               f"{sp.total_time_s_std:.3f}"])
        doc.table([["Modèle", "Éch.", "Best p", "Total sk (s)", "Total Spark (s)", "Ratio", "Écart-type Spark"]] +
                  total_rows, [.6, .5, .5, 1, 1, .6, 1.1], size=7, row_h=.22)
        doc.para("Best p minimise ici le temps total, indépendamment du meilleur fit. "
                 "Résultats individuels et dispersion des deux moteurs : benchmark_runs.csv et benchmark_results.csv.", size=7)

        cluster_csv = csv_path.parent / "cluster" / "benchmark_results.csv"
        if cluster_csv.exists():
            add_cluster_section(doc, df, cluster_csv, models, usable, env)
        doc.close()
    return out_path


if __name__ == "__main__":
    print(build_report())
