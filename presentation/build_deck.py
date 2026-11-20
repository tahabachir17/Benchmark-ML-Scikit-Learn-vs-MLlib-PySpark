"""Builds presentation/Benchmark_ML_Presentation.pptx from the benchmark results.

    python presentation/build_deck.py

Numbers come from results/benchmark_results.csv (local) and
results/cluster/benchmark_results.csv (Docker cluster); charts are native PowerPoint charts.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import (XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE,
                            XL_TICK_LABEL_POSITION)
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation" / "Benchmark_ML_Presentation.pptx"
ASSETS = ROOT / "presentation" / "assets"

# ------------------------------------------------------------------ palette & fonts
FOREST = RGBColor(0x14, 0x4D, 0x2C)      # dominant: dark green (title / conclusion)
GREEN = RGBColor(0x1E, 0x7B, 0x3C)       # headings, accents
TINT = RGBColor(0xEE, 0xF6, 0xF0)        # card background
MINT = RGBColor(0xC8, 0xF0, 0xD4)
INK = RGBColor(0x1A, 0x1A, 0x1A)
INK2 = RGBColor(0x55, 0x55, 0x52)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRIDC = RGBColor(0xE2, 0xE2, 0xDE)
SKLEARN = RGBColor(0xEB, 0x68, 0x34)     # same encoding as the PDF report
SPARK = RGBColor(0x2A, 0x78, 0xD6)
CLUSTER = RGBColor(0x1B, 0xAF, 0x7A)
NEUTRAL = RGBColor(0x8A, 0x8A, 0x85)
HEAD, BODY, MONO = "Cambria", "Calibri", "Courier New"

W, H = Inches(13.333), Inches(7.5)
PRESENTER = {"A": "Taha Bachir El Bouhali", "B": "Hsain Zaid"}
SUPERVISOR = "Encadré par : Pr. Abderrahim Elqadi"
MX = Inches(0.6)


# ------------------------------------------------------------------ data
local = pd.read_csv(ROOT / "results" / "benchmark_results.csv")
cluster = pd.read_csv(ROOT / "results" / "cluster" / "benchmark_results.csv")
raw = pd.read_csv(ROOT / "data" / "insurance.csv")
SCALES = sorted(local.scale.unique())
CLU_SCALES = sorted(cluster.scale.unique())


def sk(df, m, s):
    return df[(df.framework == "sklearn") & (df.model == m) & (df.scale == s)].iloc[0]


def best(df, m, s, col="fit_time_s"):
    g = df[(df.framework == "spark") & (df.model == m) & (df.scale == s)]
    return g.loc[g[col].idxmin()]


def spark_at(df, m, s, p):
    return df[(df.framework == "spark") & (df.model == m) & (df.scale == s) & (df.partitions == p)].iloc[0]


def fr(x, d=1):
    """French decimal formatting."""
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


SMAX = max(SCALES)
N_TRAIN_MAX = int(sk(local, "lr", SMAX).n_train)
cross = {m: (sk(local, m, SMAX), best(local, m, SMAX)) for m in ("lr", "rf")}
tot = {m: (sk(local, m, SMAX).total_time_s, local[(local.framework == "spark") & (local.model == m)
                                                 & (local.scale == SMAX)].total_time_s.min())
       for m in ("lr", "rf")}


# ------------------------------------------------------------------ helpers
def text(slide, x, y, w, h, runs, size=16, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, italic=False, margin=0.05, name=None):
    """runs: str, or list of paragraphs; a paragraph is str or list of (text, {opts})."""
    tb = slide.shapes.add_textbox(x, y, w, h)
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", Inches(margin))
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        parts = para if isinstance(para, list) else [(para, {})]
        for t, o in parts:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = o.get("color", color)
        if isinstance(para, list) and para and para[0][1].get("space_after") is not None:
            p.space_after = Pt(para[0][1]["space_after"])
    return tb


def bullets(slide, x, y, w, h, items, size=16, color=INK, space=8):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(Inches(0.25)))
        pPr.set("indent", str(-Inches(0.22)))
        bu_clr = OxmlElement("a:buClr")
        srgb = OxmlElement("a:srgbClr"); srgb.set("val", "1E7B3C"); bu_clr.append(srgb)
        pPr.append(bu_clr)
        bu = OxmlElement("a:buChar"); bu.set("char", "•"); pPr.append(bu)
        p.space_after = Pt(space)
        parts = it if isinstance(it, list) else [(it, {})]
        for t, o in parts:
            r = p.add_run(); r.text = t
            r.font.name = BODY; r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", False); r.font.color.rgb = o.get("color", color)
    return tb


def box(slide, x, y, w, h, fill=TINT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, line=None, radius=0.08):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    s.fill.solid(); s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line; s.line.width = Pt(1.25)
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def badge(slide, x, y, label, d=0.55, fill=GREEN, color=WHITE, size=18):
    """Motif: a filled circle carrying a number or letter."""
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, Inches(d), Inches(d))
    c.fill.solid(); c.fill.fore_color.rgb = fill; c.line.fill.background(); c.shadow.inherit = False
    tf = c.text_frame
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", 0)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = label
    r.font.name = HEAD; r.font.size = Pt(size); r.font.bold = True; r.font.color.rgb = color
    return c


def title(slide, t, presenter):
    text(slide, MX, Inches(0.38), Inches(9.6), Inches(0.9), t, size=34, bold=True, font=HEAD,
         color=FOREST, anchor=MSO_ANCHOR.MIDDLE, name="Title")
    # who presents this slide (helps the pair rehearse); small pill top-right
    pill = box(slide, Inches(10.35), Inches(0.58), Inches(2.4), Inches(0.42), fill=TINT, radius=0.5)
    pill.name = "Presenter"
    tf = pill.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", 0)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = PRESENTER[presenter]
    r.font.name = BODY; r.font.size = Pt(11); r.font.bold = True; r.font.color.rgb = GREEN


def footer(slide, n):
    text(slide, MX, Inches(7.0), Inches(9), Inches(0.3),
         "Mini-projet 08 · Benchmark Scikit-Learn vs PySpark MLlib", size=10, color=INK2)
    text(slide, Inches(11.73), Inches(7.0), Inches(1.0), Inches(0.3), str(n), size=10, color=INK2,
         align=PP_ALIGN.RIGHT)


def bg(slide, color):
    f = slide.background.fill; f.solid(); f.fore_color.rgb = color


def style_chart(chart, legend=True, size=12):
    chart.font.name = BODY
    chart.font.size = Pt(size)
    chart.font.color.rgb = INK2
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(size)
    va = chart.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = GRIDC
    va.major_gridlines.format.line.width = Pt(0.75)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(size)
    ca = chart.category_axis
    ca.format.line.color.rgb = GRIDC
    ca.tick_labels.font.size = Pt(size)
    ca.has_major_gridlines = False


def log_axis(axis, chart=None):
    if chart is not None:  # keep category labels at the bottom, not where the axes cross (1.0)
        chart.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    scaling = axis._element.find(qn("c:scaling"))
    lb = OxmlElement("c:logBase"); lb.set("val", "10")
    scaling.insert(0, lb)


def axis_title(axis, t, size=12):
    axis.has_title = True
    tf = axis.axis_title.text_frame
    tf.text = t
    r = tf.paragraphs[0].runs[0]
    r.font.size = Pt(size); r.font.bold = False; r.font.color.rgb = INK2; r.font.name = BODY


def color_line(series, rgb, dash=False, marker=XL_MARKER_STYLE.CIRCLE, width=2.5):
    ln = series.format.line
    ln.color.rgb = rgb; ln.width = Pt(width)
    if dash:
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        ln.dash_style = MSO_LINE_DASH_STYLE.DASH
    series.smooth = False
    series.marker.style = marker
    series.marker.size = 8
    series.marker.format.fill.solid(); series.marker.format.fill.fore_color.rgb = rgb
    series.marker.format.line.color.rgb = WHITE


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


# ------------------------------------------------------------------ deck
prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]
n = 0


def new_slide(dark=False):
    global n
    n += 1
    s = prs.slides.add_slide(BLANK)
    bg(s, FOREST if dark else WHITE)
    return s


# 1 ---------------------------------------------------------------- title
s = new_slide(dark=True)
text(s, MX, Inches(1.1), Inches(4), Inches(0.4), "MINI-PROJET 08", size=14, bold=True, color=MINT)
text(s, MX, Inches(1.6), Inches(8.3), Inches(2.0),
     ["Benchmark ML :", "Scikit-Learn vs PySpark MLlib"], size=42, bold=True, font=HEAD, color=WHITE)
text(s, MX, Inches(3.75), Inches(8.0), Inches(0.9),
     "Prédire les dépenses de santé et mesurer quand le calcul distribué devient rentable",
     size=18, color=MINT)
text(s, MX, Inches(5.6), Inches(8), Inches(0.5), "Présenté par : Taha Bachir El Bouhali & Hsain Zaid",
     size=16, color=WHITE)
text(s, MX, Inches(6.05), Inches(8), Inches(0.5), SUPERVISOR, size=14, color=MINT)
stats = [(fr(N_TRAIN_MAX / 1e6, 2) + " M", "lignes d'entraînement max."),
         (str(len(local[local.framework == "spark"])), "configurations Spark mesurées"),
         ("2", "environnements Spark : local et cluster")]
card = box(s, Inches(9.2), Inches(0.35), Inches(3.5), Inches(1.4), fill=WHITE, radius=0.12)
card.name = "Logo card"
logo_h = Inches(1.2)
logo_w = int(logo_h * 300 / 157)  # logo_ensam.png is 300 x 157 px
s.shapes.add_picture(str(ASSETS / "logo_ensam.png"), Inches(9.2) + (Inches(3.5) - logo_w) // 2,
                     Inches(0.45), height=logo_h).name = "Logo ENSAM Rabat"
for i, (big, small) in enumerate(stats):
    y = Inches(2.0 + i * 1.42)
    box(s, Inches(9.2), y, Inches(3.5), Inches(1.25), fill=GREEN, radius=0.12)
    text(s, Inches(9.45), y + Inches(0.1), Inches(3.1), Inches(0.65), big, size=30, bold=True,
         font=HEAD, color=WHITE)
    text(s, Inches(9.45), y + Inches(0.72), Inches(3.1), Inches(0.5), small, size=13, color=MINT)
notes(s, "Taha — Accueil (30 s). Se présenter, annoncer le sujet : comparer scikit-learn "
         "(une machine) et PySpark MLlib (calcul distribué) sur un même problème de régression, "
         "et chercher à partir de quel volume Spark devient intéressant.")

# 2 ---------------------------------------------------------------- objective
s = new_slide()
title(s, "Objectif du projet", "A")
box(s, MX, Inches(1.6), Inches(5.6), Inches(4.9), fill=FOREST, radius=0.06)
text(s, Inches(0.95), Inches(1.95), Inches(5.0), Inches(0.5), "LA QUESTION", size=13, bold=True,
     color=MINT)
text(s, Inches(0.95), Inches(2.45), Inches(5.0), Inches(3.0),
     "À partir de quel volume de données Spark MLlib devient-il plus rapide que scikit-learn ?",
     size=28, italic=True, font=HEAD, color=WHITE)
text(s, Inches(0.95), Inches(5.35), Inches(5.0), Inches(0.9),
     "Et quel est le coût de la parallélisation : partitions, shuffle, mémoire ?",
     size=15, color=MINT)
rows = [("1", "Prédire", "Régression des dépenses de santé individuelles (charges) : "
                         "Régression Linéaire et Random Forest."),
        ("2", "Comparer", "scikit-learn sur une seule machine contre PySpark MLlib en local[*] "
                          "et sur un cluster standalone."),
        ("3", "Mesurer", "Temps, précision, mémoire et shuffle selon le volume et le nombre de "
                         "partitions (2, 8, 16, 32).")]
for i, (k, head, body) in enumerate(rows):
    y = Inches(1.75 + i * 1.6)
    badge(s, Inches(6.75), y, k)
    text(s, Inches(7.55), y - Inches(0.05), Inches(5.2), Inches(0.45), head, size=20, bold=True,
         font=HEAD, color=GREEN)
    text(s, Inches(7.55), y + Inches(0.42), Inches(5.2), Inches(1.0), body, size=15, color=INK)
footer(s, n)
notes(s, "Taha (1 min). Poser la question centrale du projet. Expliquer les trois axes : "
         "la tâche de régression, les deux approches comparées, et ce que l'on mesure. "
         "Insister : on ne cherche pas seulement le plus précis, mais le plus rentable selon le volume.")

# 3 ---------------------------------------------------------------- dataset
s = new_slide()
title(s, "Le jeu de données Insurance", "A")
cols = ["age", "sex", "bmi", "children", "smoker", "region", "charges"]
sample = raw.head(6)
tbl = s.shapes.add_table(len(sample) + 1, len(cols), MX, Inches(1.65), Inches(7.6), Inches(3.2)).table
widths = [0.75, 0.95, 0.85, 1.2, 1.0, 1.35, 1.5]
for j, w_ in enumerate(widths):
    tbl.columns[j].width = Inches(w_)
for j, c in enumerate(cols):
    cell = tbl.cell(0, j); cell.text = c
    cell.fill.solid(); cell.fill.fore_color.rgb = GREEN
    r = cell.text_frame.paragraphs[0].runs[0]
    r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = MONO
for i, row in enumerate(sample.itertuples(index=False), start=1):
    for j, v in enumerate(row):
        cell = tbl.cell(i, j)
        cell.text = fr(v, 2) if isinstance(v, float) else str(v)
        cell.fill.solid(); cell.fill.fore_color.rgb = WHITE if i % 2 else TINT
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT if isinstance(v, (int, float)) else PP_ALIGN.LEFT
        r = p.runs[0]; r.font.size = Pt(14); r.font.name = MONO; r.font.color.rgb = INK
text(s, MX, Inches(5.05), Inches(7.6), Inches(0.4),
     "Extrait de data/insurance.csv · cible à prédire : charges (dépenses annuelles en $)",
     size=12, color=INK2)
box(s, MX, Inches(5.6), Inches(7.6), Inches(1.15), fill=TINT)
text(s, Inches(0.85), Inches(5.7), Inches(7.2), Inches(1.0),
     [[("Agrandissement synthétique : ", {"bold": True, "color": GREEN}),
       ("chaque ligne est répliquée x10 à x2000 avec un léger bruit gaussien, après un découpage "
        "train/test commun. Ces volumes mesurent la charge de calcul, pas de nouveaux patients.", {})]],
     size=14)
for i, (big, small) in enumerate([("1 338", "lignes d'origine"),
                                   ("3 + 3", "variables catégorielles + numériques"),
                                   (fr(len(raw) * SMAX / 1e6, 2) + " M", f"lignes au volume x{SMAX}")]):
    y = Inches(1.65 + i * 1.7)
    box(s, Inches(8.7), y, Inches(4.05), Inches(1.45), fill=TINT)
    text(s, Inches(8.95), y + Inches(0.12), Inches(3.6), Inches(0.7), big, size=34, bold=True,
         font=HEAD, color=GREEN)
    text(s, Inches(8.95), y + Inches(0.85), Inches(3.6), Inches(0.5), small, size=14, color=INK2)
footer(s, n)
notes(s, "Taha (1 min). Présenter les 7 colonnes : âge, sexe, IMC, enfants, fumeur, région "
         "et la cible charges. Le jeu original est petit (1 338 lignes) : pour tester la scalabilité, "
         "on le réplique jusqu'à x2000 avec un léger bruit. Le découpage train/test est fait AVANT la "
         "réplication : les copies d'une même personne restent du même côté, il n'y a pas de fuite.")

# 4 ---------------------------------------------------------------- pipeline
s = new_slide()
title(s, "Le pipeline PySpark ML", "A")
steps = [("CSV", "insurance.csv\nschéma typé"),
         ("StringIndexer", "sex, smoker,\nregion → index"),
         ("OneHotEncoder", "index →\nvecteurs binaires"),
         ("VectorAssembler", "+ age, bmi, children\n→ features"),
         ("Modèle", "LinearRegression\nou RandomForest"),
         ("Évaluation", "RMSE · R² · MAE\nRegressionEvaluator")]
bw, gap, y0 = Inches(1.78), Inches(0.31), Inches(1.75)
for i, (head, sub) in enumerate(steps):
    x = MX + i * (bw + gap)
    fill = GREEN if head in ("Modèle",) else TINT
    b = box(s, x, y0, bw, Inches(1.75), fill=fill)
    text(s, x, y0 + Inches(0.2), bw, Inches(0.5), head, size=15, bold=True, font=BODY,
         color=WHITE if fill == GREEN else GREEN, align=PP_ALIGN.CENTER)
    text(s, x + Inches(0.08), y0 + Inches(0.75), bw - Inches(0.16), Inches(0.9), sub.split("\n"),
         size=13, color=WHITE if fill == GREEN else INK, align=PP_ALIGN.CENTER)
    if i < len(steps) - 1:
        a = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x + bw + Inches(0.03), y0 + Inches(0.875),
                                   x + bw + gap - Inches(0.03), y0 + Inches(0.875))
        a.line.color.rgb = GREEN; a.line.width = Pt(2.25)
        a.line._get_or_add_ln().append(_tail := OxmlElement("a:tailEnd"))
        _tail.set("type", "triangle")
code = ("indexers  = [StringIndexer(inputCol=c, outputCol=c + \"_idx\") for c in CAT]\n"
        "encoder   = OneHotEncoder(inputCols=[...], outputCols=[...])\n"
        "assembler = VectorAssembler(inputCols=NUM + OHE, outputCol=\"features\")\n"
        "model     = RandomForestRegressor(numTrees=20, maxDepth=5)\n"
        "pipeline  = Pipeline(stages=indexers + [encoder, assembler, model])")
box(s, MX, Inches(3.95), Inches(7.9), Inches(2.7), fill=RGBColor(0x0F, 0x2A, 0x1B))
text(s, Inches(0.85), Inches(4.1), Inches(7.5), Inches(0.35), "insurance_pipeline.py", size=12,
     bold=True, color=MINT)
text(s, Inches(0.85), Inches(4.5), Inches(7.5), Inches(2.1), code.split("\n"), size=12, font=MONO,
     color=RGBColor(0xE6, 0xF4, 0xEA))
bullets(s, Inches(8.85), Inches(4.0), Inches(3.9), Inches(2.7), [
    [("Même prétraitement ", {"bold": True}), ("côté scikit-learn (ColumnTransformer + OneHotEncoder)", {})],
    [("Mêmes hyper-paramètres : ", {"bold": True}), ("20 arbres, profondeur 5", {})],
    [("Script de benchmark : ", {"bold": True}), ("benchmark_sklearn_spark.py", {})],
], size=14)
footer(s, n)
notes(s, "Taha (1 min 30). Suivre le flux de gauche à droite : on lit le CSV, on transforme "
         "les variables texte en index (StringIndexer), puis en vecteurs binaires (OneHotEncoder), on "
         "assemble toutes les variables dans un seul vecteur (VectorAssembler), on entraîne le modèle "
         "puis on évalue. Mini-démo possible : python insurance_pipeline.py --model both (30 s).")

# 5 ---------------------------------------------------------------- protocol
s = new_slide()
title(s, "Protocole de benchmark", "A")
cards = [("Équité", ["Un seul découpage train/test 80/20, partagé par les deux frameworks",
                     "Mêmes variables, mêmes hyper-paramètres",
                     "Échauffement JVM et scikit-learn exclu des mesures"]),
         ("Grille testée", [f"{len(SCALES)} volumes : " + ", ".join(f"x{v}" for v in SCALES),
                            "4 nombres de partitions : 2, 8, 16, 32",
                            "2 modèles · 3 répétitions, médiane retenue"]),
         ("Temps mesurés", ["Fit : entraînement du pipeline",
                            "Inférence : prédictions forcées sur le jeu de test",
                            "Total : lecture + préparation + fit + prédiction"]),
         ("Qualité et ressources", ["R², RMSE, MAE sur le même jeu de test",
                                    "Pic mémoire RSS (Python + JVM), toutes les 50 ms",
                                    "Octets de shuffle via l'API REST de Spark"])]
cw, ch = Inches(5.95), Inches(2.45)
for i, (head, items) in enumerate(cards):
    x = MX + (i % 2) * (cw + Inches(0.25))
    y = Inches(1.6) + (i // 2) * (ch + Inches(0.25))
    box(s, x, y, cw, ch, fill=TINT)
    badge(s, x + Inches(0.25), y + Inches(0.25), str(i + 1), d=0.5, size=16)
    text(s, x + Inches(0.9), y + Inches(0.24), cw - Inches(1.1), Inches(0.5), head, size=20, bold=True,
         font=HEAD, color=GREEN)
    bullets(s, x + Inches(0.3), y + Inches(0.9), cw - Inches(0.5), ch - Inches(1.0), items, size=14,
            space=5)
footer(s, n)
notes(s, "Taha (1 min 30). Insister sur l'équité de la comparaison : même découpage, mêmes "
         "paramètres, médiane de 3 répétitions pour lisser le bruit. Préciser qu'on mesure le temps "
         "d'entraînement seul ET le temps total, ce qui sera important pour la conclusion.")

# 6 ---------------------------------------------------------------- environments
s = new_slide()
title(s, "Trois environnements comparés", "A")
envs = [("scikit-learn", "Mono-nœud", SKLEARN,
         ["Données entièrement en RAM (pandas / NumPy)", "Random Forest : tous les cœurs (n_jobs=-1)",
          "Aucun coût de distribution"]),
        ("Spark local[*]", "1 machine · 8 cœurs", SPARK,
         ["Un seul processus JVM", "Une tâche par partition, réparties sur 8 cœurs",
          "Shuffle en mémoire locale"]),
        ("Spark standalone", "Master + 2 workers", CLUSTER,
         ["Conteneurs Docker : 2 workers x 2 cœurs", "Exécuteurs séparés de 1 Go chacun",
          "Échanges via le réseau Docker"])]
cw = Inches(3.9)
for i, (head, sub, colr, items) in enumerate(envs):
    x = MX + i * (cw + Inches(0.2))
    box(s, x, Inches(1.6), cw, Inches(4.6), fill=TINT)
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.3), Inches(1.9), Inches(0.42), Inches(0.42))
    c.fill.solid(); c.fill.fore_color.rgb = colr; c.line.fill.background(); c.shadow.inherit = False
    text(s, x + Inches(0.85), Inches(1.82), cw - Inches(1.0), Inches(0.55), head, size=22, bold=True,
         font=HEAD, color=INK, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + Inches(0.3), Inches(2.5), cw - Inches(0.5), Inches(0.4), sub, size=15, bold=True,
         color=GREEN)
    bullets(s, x + Inches(0.3), Inches(3.1), cw - Inches(0.55), Inches(2.9), items, size=15, space=10)
text(s, MX, Inches(6.35), Inches(12.1), Inches(0.5),
     "Les couleurs orange (scikit-learn), bleu (Spark local) et vert (cluster) se retrouvent sur tous les graphiques.",
     size=13, italic=True, color=INK2)
footer(s, n)
notes(s, "Taha (1 min), puis transition : « Maintenant que le protocole est posé, "
         "[prénom B] va vous présenter ce que les mesures montrent. » Les trois environnements vont du "
         "plus simple (tout en RAM) au plus distribué (master + workers séparés).")

# 7 ---------------------------------------------------------------- time vs volume
s = new_slide()
title(s, "Temps d'entraînement selon le volume", "B")
for k, m in enumerate(("lr", "rf")):
    cd = CategoryChartData()
    cd.categories = [f"x{v}" for v in SCALES]
    cd.add_series("scikit-learn", [round(sk(local, m, v).fit_time_s, 3) for v in SCALES])
    cd.add_series("Spark local[*] (meilleur p)", [round(best(local, m, v).fit_time_s, 3) for v in SCALES])
    x = MX + k * Inches(6.15)
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, x, Inches(1.45), Inches(5.95), Inches(4.4), cd)
    ch_ = gf.chart
    style_chart(ch_)
    ch_.has_title = True
    ch_.chart_title.text_frame.text = "Régression Linéaire" if m == "lr" else "Random Forest"
    tr = ch_.chart_title.text_frame.paragraphs[0].runs[0]
    tr.font.size = Pt(16); tr.font.bold = True; tr.font.color.rgb = INK; tr.font.name = BODY
    log_axis(ch_.value_axis, ch_)
    ch_.value_axis.tick_labels.number_format = '0.0#'
    ch_.value_axis.tick_labels.number_format_is_linked = False
    axis_title(ch_.value_axis, "Fit (s, échelle log)")
    color_line(ch_.plots[0].series[0], SKLEARN)
    color_line(ch_.plots[0].series[1], SPARK, marker=XL_MARKER_STYLE.SQUARE)
fixed = local[(local.framework == "spark") & (local.scale == 1)].fit_time_s.min()
box(s, MX, Inches(6.0), Inches(12.1), Inches(0.85), fill=TINT)
text(s, Inches(0.85), Inches(6.05), Inches(11.7), Inches(0.75),
     [[("Coût fixe de Spark ≈ " + fr(fixed) + " s ", {"bold": True, "color": GREEN}),
       ("même sur 1 070 lignes (planification des jobs, JVM, tâches). scikit-learn est alors "
        "15 à 100 fois plus rapide ; l'écart se réduit quand le volume augmente.", {})]],
     size=15, anchor=MSO_ANCHOR.MIDDLE)
footer(s, n)
notes(s, "Hsain (1 min 30). Lire les deux graphiques (échelle logarithmique). La courbe orange "
         "(scikit-learn) part de quelques millisecondes et monte avec le volume. La courbe bleue (Spark) "
         "est presque plate au début : c'est le coût fixe d'environ 2 secondes. Les deux courbes se "
         "rapprochent puis se croisent au plus grand volume.")

# 8 ---------------------------------------------------------------- crossover
s = new_slide()
title(s, "Le seuil de basculement", "B")
cd = CategoryChartData()
cd.categories = [f"x{v}" for v in SCALES]
for m, label in (("lr", "Régression Linéaire"), ("rf", "Random Forest")):
    cd.add_series(label, [round(best(local, m, v).fit_time_s / sk(local, m, v).fit_time_s, 3) for v in SCALES])
cd.add_series("Égalité : au-dessus, Spark plus lent", [1.0] * len(SCALES))
gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, MX, Inches(1.45), Inches(7.3), Inches(5.35), cd)
ch_ = gf.chart
style_chart(ch_)
log_axis(ch_.value_axis, ch_)
ch_.value_axis.tick_labels.number_format = '0.0#"x"'
ch_.value_axis.tick_labels.number_format_is_linked = False
axis_title(ch_.value_axis, "Fit Spark / fit scikit-learn (log)")
axis_title(ch_.category_axis, "Volume (facteur de réplication)")
color_line(ch_.plots[0].series[0], SPARK)
color_line(ch_.plots[0].series[1], CLUSTER, marker=XL_MARKER_STYLE.SQUARE)
eq = ch_.plots[0].series[2]
color_line(eq, NEUTRAL, dash=True, width=1.75)
eq.marker.style = XL_MARKER_STYLE.NONE
for i, m in enumerate(("lr", "rf")):
    sk_, sp_ = cross[m]
    y = Inches(1.5 + i * 2.0)
    box(s, Inches(8.2), y, Inches(4.55), Inches(1.8), fill=TINT)
    text(s, Inches(8.45), y + Inches(0.1), Inches(4.1), Inches(0.4),
         ("Régression Linéaire" if m == "lr" else "Random Forest") + f" · x{SMAX}",
         size=15, bold=True, color=GREEN)
    text(s, Inches(8.45), y + Inches(0.48), Inches(4.1), Inches(0.75),
         fr(sk_.fit_time_s / sp_.fit_time_s) + "x plus rapide", size=30, bold=True, font=HEAD, color=INK)
    text(s, Inches(8.45), y + Inches(1.2), Inches(4.1), Inches(0.5),
         f"Spark {fr(sp_.fit_time_s)} s contre scikit-learn {fr(sk_.fit_time_s)} s (p={int(sp_.partitions)})",
         size=13, color=INK2)
box(s, Inches(8.2), Inches(5.5), Inches(4.55), Inches(1.3), fill=FOREST)
text(s, Inches(8.45), Inches(5.58), Inches(4.1), Inches(1.15),
     [[("Nuance : ", {"bold": True, "color": MINT}),
       ("en temps total, Spark reste plus lent (" + fr(tot['lr'][1] / tot['lr'][0], 2) + "x en LR, "
        + fr(tot['rf'][1] / tot['rf'][0], 2) + "x en RF) : lecture et préparation coûtent encore.", {})]],
     size=14, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
footer(s, n)
notes(s, "Hsain (2 min) — diapositive clé. Le graphique montre le rapport temps Spark / temps "
         "scikit-learn : au-dessus de la ligne pointillée, Spark est plus lent. Le rapport descend de "
         "plus de 100x à moins de 1 : le basculement a lieu entre x1000 et x2000, soit entre 1 et 2 "
         "millions de lignes d'entraînement, pour les deux modèles. C'est mesuré, pas extrapolé. "
         "Nuance importante : en temps total (lecture + préparation + entraînement + prédiction), "
         "Spark est encore légèrement plus lent.")

# 9 ---------------------------------------------------------------- partitions
s = new_slide()
title(s, "Impact du nombre de partitions", "B")
parts = [2, 8, 16, 32]
for k, m in enumerate(("lr", "rf")):
    cd = CategoryChartData()
    cd.categories = [f"{p} part." for p in parts]
    cd.add_series(f"Spark x{SMAX}", [round(spark_at(local, m, SMAX, p).fit_time_s, 2) for p in parts])
    x = MX + k * Inches(4.15)
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, Inches(1.45), Inches(4.0), Inches(4.3), cd)
    ch_ = gf.chart
    style_chart(ch_, legend=False)
    ch_.has_title = True
    ch_.chart_title.text_frame.text = ("Régression Linéaire" if m == "lr" else "Random Forest") + f" (x{SMAX})"
    tr = ch_.chart_title.text_frame.paragraphs[0].runs[0]
    tr.font.size = Pt(15); tr.font.bold = True; tr.font.color.rgb = INK; tr.font.name = BODY
    axis_title(ch_.value_axis, "Fit (s)")
    plot = ch_.plots[0]; plot.gap_width = 60
    ser = plot.series[0]; ser.format.fill.solid(); ser.format.fill.fore_color.rgb = SPARK
    bestp = parts.index(int(best(local, m, SMAX).partitions))
    pt = ser.points[bestp]; pt.format.fill.solid(); pt.format.fill.fore_color.rgb = GREEN
    plot.has_data_labels = True
    dl = plot.data_labels; dl.number_format = '0.0" s"'; dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END; dl.font.size = Pt(12); dl.font.color.rgb = INK
    text(s, x, Inches(5.8), Inches(4.0), Inches(0.4),
         f"scikit-learn : {fr(sk(local, m, SMAX).fit_time_s)} s · en vert : meilleur choix",
         size=12, color=INK2, align=PP_ALIGN.CENTER)
small = local[(local.framework == "spark") & (local.scale == 1)].groupby("partitions").fit_time_s.mean()
big = local[(local.framework == "spark") & (local.scale == SMAX)].groupby("partitions").fit_time_s.mean()
box(s, Inches(9.05), Inches(1.5), Inches(3.7), Inches(2.45), fill=TINT)
text(s, Inches(9.3), Inches(1.6), Inches(3.3), Inches(0.4), "Petit volume (x1)", size=16, bold=True,
     color=GREEN)
text(s, Inches(9.3), Inches(2.05), Inches(3.3), Inches(1.8),
     f"Passer de 2 à 32 partitions ralentit le fit de {fr((small[32] / small[2] - 1) * 100, 0)} % : "
     "plus de tâches et de shuffle, sans gain de calcul.", size=14)
box(s, Inches(9.05), Inches(4.15), Inches(3.7), Inches(2.45), fill=TINT)
text(s, Inches(9.3), Inches(4.25), Inches(3.3), Inches(0.4), f"Grand volume (x{SMAX})", size=16,
     bold=True, color=GREEN)
text(s, Inches(9.3), Inches(4.7), Inches(3.3), Inches(1.8),
     "8 partitions, une par cœur, est optimal. Avec 2, Spark n'utilise que 2 cœurs sur 8.", size=14)
footer(s, n)
notes(s, "Hsain (1 min 30). Au grand volume, 2 partitions sont trop peu : seulement 2 cœurs "
         "travaillent (26,5 s en LR). 8 partitions, une par cœur, donnent le meilleur temps. Au-delà, "
         "16 ou 32 partitions ajoutent des tâches et du shuffle et ralentissent. Sur un petit volume, "
         "multiplier les partitions est même franchement contre-productif. Règle à retenir : environ "
         "une partition par cœur disponible.")

# 10 --------------------------------------------------------------- shuffle & memory
s = new_slide()
title(s, "Shuffle et mémoire", "B")
cd = CategoryChartData()
cd.categories = [f"{p} part." for p in parts]
cd.add_series("Random Forest", [round(spark_at(local, "rf", SMAX, p).shuffle_write_mb, 1) for p in parts])
cd.add_series("Régression Linéaire", [round(spark_at(local, "lr", SMAX, p).shuffle_write_mb, 1) for p in parts])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, MX, Inches(1.45), Inches(6.9), Inches(4.7), cd)
ch_ = gf.chart
style_chart(ch_)
ch_.has_title = True
ch_.chart_title.text_frame.text = f"Shuffle écrit par run (Mo), x{SMAX}"
tr = ch_.chart_title.text_frame.paragraphs[0].runs[0]
tr.font.size = Pt(15); tr.font.bold = True; tr.font.color.rgb = INK; tr.font.name = BODY
ch_.value_axis.minimum_scale = 0
plot = ch_.plots[0]; plot.gap_width = 70; plot.overlap = -10
for ser, colr in zip(plot.series, (SPARK, RGBColor(0x9C, 0xC2, 0xEE))):
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = colr
plot.series[0].data_labels.show_value = True
plot.series[0].data_labels.number_format = '0'
plot.series[0].data_labels.number_format_is_linked = False
plot.series[0].data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
plot.series[0].data_labels.font.size = Pt(12)
text(s, MX, Inches(6.2), Inches(6.9), Inches(0.5),
     "Le Random Forest échange plus de données quand les partitions augmentent (agrégation des histogrammes).",
     size=12, color=INK2)
sk_mem = sk(local, "rf", SMAX).peak_mem_mb / 1024
sp_mem = local[(local.framework == "spark") & (local.model == "rf") & (local.scale == SMAX)].peak_mem_mb.max() / 1024
for i, (big_, lab, colr) in enumerate([(fr(sk_mem) + " Go", "pic mémoire scikit-learn (Random Forest, x%d)" % SMAX, SKLEARN),
                                         (fr(sp_mem) + " Go", "pic mémoire Spark : pilote Python + JVM", SPARK)]):
    y = Inches(1.5 + i * 1.8)
    box(s, Inches(7.85), y, Inches(4.9), Inches(1.6), fill=TINT)
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(8.1), y + Inches(0.3), Inches(0.35), Inches(0.35))
    c.fill.solid(); c.fill.fore_color.rgb = colr; c.line.fill.background(); c.shadow.inherit = False
    text(s, Inches(8.6), y + Inches(0.12), Inches(4.0), Inches(0.75), big_, size=34, bold=True, font=HEAD)
    text(s, Inches(8.6), y + Inches(0.9), Inches(4.0), Inches(0.6), lab, size=14, color=INK2)
box(s, Inches(7.85), Inches(5.15), Inches(4.9), Inches(1.55), fill=FOREST)
text(s, Inches(8.1), Inches(5.22), Inches(4.45), Inches(1.4),
     "La JVM réserve sa mémoire d'avance : Spark consomme environ 1 Go même pour 1 070 lignes.",
     size=14, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
footer(s, n)
notes(s, "Hsain (1 min). Le shuffle est l'échange de données entre partitions : il augmente "
         "avec le nombre de partitions, surtout pour le Random Forest. Côté mémoire, Spark a un plancher "
         "élevé à cause de la JVM. Limite à annoncer : on mesure la mémoire du pilote ; la JVM réutilisée "
         "peut garder de la mémoire d'un essai à l'autre.")

# 11 --------------------------------------------------------------- accuracy
s = new_slide()
title(s, "Précision : des modèles comparables", "B")
hdr = ["Modèle", "Volume", "R² scikit-learn", "R² Spark", "RMSE scikit-learn", "RMSE Spark"]
rows_ = []
for m in ("lr", "rf"):
    for v in (1, SMAX):
        a, b = sk(local, m, v), best(local, m, v)
        rows_.append(["Rég. Linéaire" if m == "lr" else "Random Forest", f"x{v}", fr(a.r2, 4), fr(b.r2, 4),
                      fr(a.rmse, 0) + " $", fr(b.rmse, 0) + " $"])
tbl = s.shapes.add_table(len(rows_) + 1, len(hdr), MX, Inches(1.6), Inches(8.2), Inches(2.9)).table
for j, w_ in enumerate([1.65, 0.9, 1.45, 1.1, 1.85, 1.25]):
    tbl.columns[j].width = Inches(w_)
for j, c in enumerate(hdr):
    cell = tbl.cell(0, j); cell.text = c; cell.fill.solid(); cell.fill.fore_color.rgb = GREEN
    r = cell.text_frame.paragraphs[0].runs[0]; r.font.size = Pt(14); r.font.bold = True
    r.font.color.rgb = WHITE; r.font.name = BODY
for i, row in enumerate(rows_, start=1):
    for j, v in enumerate(row):
        cell = tbl.cell(i, j); cell.text = v; cell.fill.solid()
        cell.fill.fore_color.rgb = WHITE if i % 2 else TINT
        p = cell.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.LEFT if j < 2 else PP_ALIGN.RIGHT
        r = p.runs[0]; r.font.size = Pt(14); r.font.name = BODY; r.font.color.rgb = INK
for i, (k, head, body) in enumerate([
        ("=", "Régression Linéaire identique", "Même R² et même RMSE au chiffre près : la preuve que les deux "
                                                "frameworks voient exactement le même jeu de test."),
        ("≈", "Random Forest proche", "Spark découpe les variables continues en intervalles (maxBins) ; "
                                      "scikit-learn teste les seuils exacts. Même nombre d'arbres, pas le même algorithme.")]):
    y = Inches(4.8 + i * 1.0)
    badge(s, MX, y, k, d=0.5, size=18)
    text(s, Inches(1.3), y - Inches(0.05), Inches(7.5), Inches(0.95),
         [[(head + " : ", {"bold": True, "color": GREEN}), (body, {})]], size=14)
box(s, Inches(9.15), Inches(1.6), Inches(3.6), Inches(5.1), fill=FOREST)
text(s, Inches(9.4), Inches(1.85), Inches(3.1), Inches(0.4), "À RETENIR", size=13, bold=True, color=MINT)
text(s, Inches(9.4), Inches(2.35), Inches(3.1), Inches(4.2),
     ["Le choix entre scikit-learn et Spark est une question de coût et de volume, pas de précision.",
      "", "Le Random Forest explique environ 87 à 89 % de la variance des dépenses."],
     size=17, color=WHITE, font=HEAD)
footer(s, n)
notes(s, "Hsain ou Taha (1 min). La Régression Linéaire donne exactement le même R² des deux côtés : "
         "c'est la preuve que le découpage train/test est bien commun. Le Random Forest diffère "
         "légèrement car les implémentations ne sont pas identiques (Spark utilise des intervalles, "
         "maxBins=32). Le choix du framework ne change donc pas la qualité, seulement le coût.")

# 12 --------------------------------------------------------------- local vs cluster
s = new_slide()
title(s, "Mono-nœud vs cluster Spark standalone", "B")
_src = Image.open(ASSETS / "spark_master_ui.jpg")
_top, _apps = _src.crop((0, 0, 800, 305)), _src.crop((0, 392, 800, 495))
ui = Image.new("RGB", (800, _top.height + _apps.height), "white")
ui.paste(_top, (0, 0)); ui.paste(_apps, (0, _top.height))
ui_path = ASSETS / "spark_master_ui_crop.png"; ui.save(ui_path)
pic_w = Inches(5.6)
pic = s.shapes.add_picture(str(ui_path), MX, Inches(1.5), width=pic_w)
pic.line.color.rgb = GRIDC; pic.line.width = Pt(1)
text(s, MX, Inches(1.5) + pic.height + Inches(0.08), pic_w, Inches(0.6),
     "Interface du master Spark : 2 workers vivants, 4 cœurs, application de benchmark terminée (34 min).",
     size=12, color=INK2)
for i, (big_, small_) in enumerate([("2", "workers vivants"), ("4", "cœurs exécuteurs"), ("34 min", "run complet")]):
    x = MX + i * Inches(1.93)
    box(s, x, Inches(5.5), Inches(1.75), Inches(1.25), fill=TINT)
    text(s, x, Inches(5.55), Inches(1.75), Inches(0.65), big_, size=26, bold=True, font=HEAD, color=GREEN,
         align=PP_ALIGN.CENTER)
    text(s, x, Inches(6.2), Inches(1.75), Inches(0.45), small_, size=13, color=INK2, align=PP_ALIGN.CENTER)
cmax = max(CLU_SCALES)
cd = CategoryChartData()
cd.categories = ["Régression Linéaire", "Random Forest"]
cd.add_series("scikit-learn (conteneur, 4 cœurs)", [round(sk(cluster, m, cmax).fit_time_s, 2) for m in ("lr", "rf")])
cd.add_series("Spark local[*] (8 cœurs)", [round(best(local, m, cmax).fit_time_s, 2) for m in ("lr", "rf")])
cd.add_series("Spark cluster (2 workers)", [round(best(cluster, m, cmax).fit_time_s, 2) for m in ("lr", "rf")])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(6.5), Inches(1.45), Inches(6.25), Inches(3.9), cd)
ch_ = gf.chart
style_chart(ch_)
ch_.has_title = True
ch_.chart_title.text_frame.text = f"Temps d'entraînement à x{cmax} (s)"
tr = ch_.chart_title.text_frame.paragraphs[0].runs[0]
tr.font.size = Pt(15); tr.font.bold = True; tr.font.color.rgb = INK; tr.font.name = BODY
plot = ch_.plots[0]; plot.gap_width = 55; plot.overlap = -5
for ser, colr in zip(plot.series, (SKLEARN, SPARK, CLUSTER)):
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = colr
plot.has_data_labels = True
dl = plot.data_labels; dl.number_format = '0.0'; dl.number_format_is_linked = False
dl.position = XL_LABEL_POSITION.OUTSIDE_END; dl.font.size = Pt(12); dl.font.color.rgb = INK
slow = [best(cluster, m, cmax).fit_time_s / best(local, m, cmax).fit_time_s for m in ("lr", "rf")]
box(s, Inches(6.5), Inches(5.5), Inches(6.25), Inches(1.25), fill=TINT)
text(s, Inches(6.75), Inches(5.55), Inches(5.8), Inches(1.15),
     [[("Pas de basculement sur le cluster jusqu'à x%d. " % cmax, {"bold": True, "color": GREEN}),
       (f"Il est {fr((min(slow) - 1) * 100, 0)} à {fr((max(slow) - 1) * 100, 0)} % plus lent que local[*] : "
        "2 fois moins de cœurs et des échanges réseau entre exécuteurs.", {})]],
     size=14, anchor=MSO_ANCHOR.MIDDLE)
footer(s, n)
notes(s, "Hsain (1 min 30). Montrer la capture : c'est un vrai ordonnanceur Spark standalone "
         "avec un master et 2 workers qui exécutent des tâches séparées. Résultat : à volume égal, le "
         "cluster est un peu plus lent que local[*], car il a 4 cœurs au lieu de 8 et les exécuteurs "
         "échangent par le réseau Docker. Message : distribuer sur une seule machine ajoute du coût "
         "sans ajouter de puissance. x2000 n'a pas été lancé sur le cluster : 1 Go par exécuteur.")

# 13 --------------------------------------------------------------- limits
s = new_slide()
title(s, "Limites de l'étude", "B")
lims = [("1", "Une seule machine physique", "Le cluster Docker démontre la distribution des tâches, "
                                            "pas le coût réseau entre machines distantes."),
        ("2", "Données synthétiques", "Les volumes agrandis mesurent la charge de calcul ; ils ne prouvent "
                                     "pas une meilleure généralisation."),
        ("3", "Mémoire du pilote seulement", "Le RSS inclut la JVM locale mais exclut les exécuteurs distants ; "
                                            "la JVM réutilisée garde de la mémoire."),
        ("4", "Environnements différents", "Windows (Python 3.11) et conteneurs (Python 3.8) : on compare les "
                                          "moteurs au sein de chaque environnement.")]
cw, ch = Inches(5.95), Inches(2.3)
for i, (k, head, body) in enumerate(lims):
    x = MX + (i % 2) * (cw + Inches(0.25))
    y = Inches(1.6) + (i // 2) * (ch + Inches(0.3))
    box(s, x, y, cw, ch, fill=TINT)
    badge(s, x + Inches(0.3), y + Inches(0.3), k, d=0.55)
    text(s, x + Inches(1.05), y + Inches(0.28), cw - Inches(1.25), Inches(0.55), head, size=19,
         bold=True, font=HEAD, color=GREEN)
    text(s, x + Inches(1.05), y + Inches(0.9), cw - Inches(1.3), Inches(1.3), body, size=15)
footer(s, n)
notes(s, "Hsain (1 min). Annoncer les limites avant le professeur : cela montre la rigueur. "
         "Piste d'amélioration : refaire le benchmark sur 2 vraies machines reliées en Ethernet "
         "pour mesurer le coût réseau (procédure prête dans CLUSTER.md).")

# 14 --------------------------------------------------------------- conclusion
s = new_slide(dark=True)
text(s, MX, Inches(0.6), Inches(12), Inches(0.9), "Conclusion", size=40, bold=True, font=HEAD, color=WHITE)
concl = [("1", "Petit et moyen volume", "scikit-learn gagne largement : le coût fixe de Spark domine."),
         ("2", "Basculement mesuré", "Entre 1 et 2 millions de lignes, Spark entraîne plus vite (1,2 à 1,3x)."),
         ("3", "Bien paramétrer", "Environ une partition par cœur : trop de partitions = trop de shuffle."),
         ("4", "Vrai gain du distribué", "Plusieurs machines ou des données qui dépassent la RAM.")]
for i, (k, head, body) in enumerate(concl):
    y = Inches(1.75 + i * 1.12)
    badge(s, MX, y, k, fill=MINT, color=FOREST)
    text(s, Inches(1.4), y - Inches(0.05), Inches(7.2), Inches(0.45), head, size=20, bold=True, font=HEAD,
         color=WHITE)
    text(s, Inches(1.4), y + Inches(0.4), Inches(7.2), Inches(0.5), body, size=15, color=MINT)
box(s, Inches(9.0), Inches(1.75), Inches(3.75), Inches(4.3), fill=GREEN, radius=0.08)
text(s, Inches(9.25), Inches(2.6), Inches(3.25), Inches(1.2), "Merci", size=40, bold=True, font=HEAD,
     color=WHITE, align=PP_ALIGN.CENTER)
text(s, Inches(9.25), Inches(3.7), Inches(3.25), Inches(0.8), "Questions ?", size=26, font=HEAD,
     color=MINT, align=PP_ALIGN.CENTER)
text(s, Inches(9.25), Inches(4.75), Inches(3.25), Inches(1.0),
     ["Code et rapport :", "benchmark_report.pdf"], size=13, color=WHITE, align=PP_ALIGN.CENTER)
notes(s, "Hsain (1 min), puis questions. Reprendre les quatre messages. Phrase de fin : "
         "« Sur une seule machine et en dessous d'un million de lignes, scikit-learn est le bon choix ; "
         "Spark devient pertinent quand les données ou le nombre de machines grandissent. »")

prs.save(OUT)
print(OUT)
