"""Builds presentation/Fiche_Revision_Benchmark.docx (study guide for the oral presentation).

    python presentation/build_fiche.py
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

OUT = Path(__file__).resolve().parent / "Fiche_Revision_Benchmark.docx"

GREEN = RGBColor(0x1E, 0x7B, 0x3C)
FOREST = RGBColor(0x14, 0x4D, 0x2C)
INK2 = RGBColor(0x55, 0x55, 0x52)
HEADER_FILL, ROW_FILL, NOTE_FILL, BORDER = "1E7B3C", "EEF6F0", "F3F8F4", "C9D8CD"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Cm(2))
sec.top_margin, sec.bottom_margin = Cm(1.8), Cm(1.8)

# ------------------------------------------------------------------ styles
st = doc.styles
normal = st["Normal"]
normal.font.name = "Calibri"; normal.font.size = Pt(11)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
normal.paragraph_format.space_after = Pt(4)
normal.paragraph_format.line_spacing = 1.1
for name, size, color, before, after in (("Title", 24, FOREST, 0, 4), ("Heading 1", 16, GREEN, 16, 6),
                                         ("Heading 2", 12.5, FOREST, 10, 4)):
    s = st[name]
    s.font.name = "Cambria"; s.font.size = Pt(size); s.font.bold = True; s.font.color.rgb = color
    rf = s.element.rPr.find(qn("w:rFonts"))
    for att in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rf is not None and rf.get(qn(att)) is not None:
            del rf.attrib[qn(att)]
    s.font.name = "Cambria"
    pf = s.paragraph_format
    pf.space_before = Pt(before); pf.space_after = Pt(after); pf.keep_with_next = True
# Title style in the default template has a bottom border; keep it subtle green
for lb in ("List Bullet", "List Number"):
    st[lb].font.name = "Calibri"; st[lb].font.size = Pt(11)
    st[lb].paragraph_format.space_after = Pt(3)


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def cell_margins(table, top=60, bottom=60, left=100, right=100):
    tblPr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for k, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        e = OxmlElement(f"w:{k}"); e.set(qn("w:w"), str(v)); e.set(qn("w:type"), "dxa"); mar.append(e)
    tblPr.append(mar)


def borders(table, color=BORDER):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:space"), "0"); e.set(qn("w:color"), color)
        b.append(e)
    tblPr.append(b)


def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    e = OxmlElement("w:tblHeader"); e.set(qn("w:val"), "true"); trPr.append(e)
    cs = OxmlElement("w:cantSplit"); trPr.append(cs)


def runs(par, text, size=None, color=None):
    """Write text with **bold** segments."""
    parts = text.split("**")
    for i, t in enumerate(parts):
        if not t:
            continue
        r = par.add_run(t)
        r.bold = (i % 2 == 1)
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color
    return par


def table(header, rows, widths_cm, size=10, first_bold=True):
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    borders(t); cell_margins(t)
    for j, w in enumerate(widths_cm):
        t.columns[j].width = Cm(w)          # tblGrid (Word reads this)
        for row in t.rows:
            row.cells[j].width = Cm(w)      # tcW (both are needed)
    if len(rows) <= 6:                      # keep small tables on one page
        for row in t.rows[:-1]:
            for c in row.cells:
                for p in c.paragraphs:
                    p.paragraph_format.keep_with_next = True
    for j, h in enumerate(header):
        c = t.rows[0].cells[j]; shade(c, HEADER_FILL)
        p = c.paragraphs[0]; p.paragraph_format.space_after = Pt(0)
        r = p.add_run(h); r.bold = True; r.font.size = Pt(size); r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    repeat_header(t.rows[0])
    for i, row in enumerate(rows, start=1):
        tr = t.rows[i]
        trPr = tr._tr.get_or_add_trPr(); trPr.append(OxmlElement("w:cantSplit"))
        for j, v in enumerate(row):
            c = tr.cells[j]
            if i % 2 == 0:
                shade(c, ROW_FILL)
            p = c.paragraphs[0]; p.paragraph_format.space_after = Pt(0)
            runs(p, f"**{v}**" if (j == 0 and first_bold and "**" not in v) else v, size=size)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def note(text, fill=NOTE_FILL):
    """A shaded one-cell box for an analogy or key idea."""
    t = doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    borders(t, color="B5D3BF"); cell_margins(t, 120, 120, 160, 160)
    c = t.rows[0].cells[0]; c.width = Cm(17); shade(c, fill)
    p = c.paragraphs[0]; p.paragraph_format.space_after = Pt(0)
    runs(p, text)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def bullet(text, style="List Bullet"):
    runs(doc.add_paragraph(style=style), text)


def h1(t):
    doc.add_heading(t, level=1)


def h2(t):
    doc.add_heading(t, level=2)


def para(t, color=None, size=None):
    return runs(doc.add_paragraph(), t, size=size, color=color)


def qa(n, q, a):
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(1); p.paragraph_format.keep_with_next = True
    r = p.add_run(f"{n}. {q}"); r.bold = True; r.font.color.rgb = FOREST
    a_p = doc.add_paragraph(); a_p.paragraph_format.left_indent = Cm(0.6); a_p.paragraph_format.space_after = Pt(6)
    runs(a_p, a)


# ------------------------------------------------------------------ footer with page numbers
fp = sec.footer.paragraphs[0]
fp.text = ""
r = fp.add_run("Mini-projet 08 · Fiche de révision · page "); r.font.size = Pt(9); r.font.color.rgb = INK2
for kind, txt in (("begin", None), (None, "PAGE"), ("end", None)):
    run = fp.add_run(); run.font.size = Pt(9); run.font.color.rgb = INK2
    if kind:
        fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), kind); run._r.append(fc)
    else:
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = txt; run._r.append(it)

# ------------------------------------------------------------------ content
doc.add_paragraph("Fiche de révision : Benchmark Scikit-Learn vs PySpark MLlib", style="Title")
para("Mini-projet 08 · Concepts, comparaisons et questions probables pour la soutenance", color=INK2)

h1("1. Ce qu'on essaie de faire")
para("On prédit les **dépenses de santé** d'une personne à partir de son âge, son IMC, s'il fume, etc. "
     "On résout ce même problème avec deux outils :")
bullet("**scikit-learn**, qui travaille sur **une seule machine** ;")
bullet("**Spark MLlib**, qui sait **répartir le calcul** sur plusieurs cœurs ou plusieurs machines.")
para("On augmente ensuite la taille des données pour trouver **à partir de quand l'outil distribué devient "
     "plus rapide**, et ce que coûte la distribution.")
note("**Image simple :** scikit-learn, c'est un cuisinier seul dans sa cuisine, très efficace pour un petit "
     "repas. Spark, c'est une brigade de cuisiniers avec un chef qui distribue les tâches. Pour 2 assiettes, "
     "la brigade perd du temps à s'organiser. Pour 2 000 assiettes, elle gagne.")

h1("2. Le Machine Learning utilisé")
table(["Concept", "Définition simple", "Dans le projet"], [
    ["Régression", "Prédire un **nombre** (et non une catégorie)", "Prédire charges en dollars"],
    ["Variable cible", "Ce qu'on veut prédire", "charges"],
    ["Variables explicatives (features)", "Les informations utilisées pour prédire",
     "age, sex, bmi, children, smoker, region"],
    ["Variable catégorielle", "Variable texte avec des valeurs fixes", "sex, smoker, region"],
    ["Variable numérique", "Variable qui est déjà un nombre", "age, bmi, children"],
    ["Régression Linéaire", "Trace la « meilleure droite » : chaque variable a un poids",
     "Modèle simple et rapide (R² ≈ 0,80)"],
    ["Random Forest", "Plusieurs arbres de décision ; la moyenne de leurs prédictions donne le résultat",
     "20 arbres, profondeur 5 (R² ≈ 0,87 à 0,89)"],
    ["Arbre de décision", "Suite de questions oui / non (« fume ? », « IMC > 30 ? ») qui mène à une prédiction",
     "Brique de base du Random Forest"],
    ["Hyper-paramètres", "Réglages choisis **avant** l'entraînement",
     "20 arbres, profondeur 5, identiques des deux côtés"],
    ["Entraînement (fit)", "Le modèle apprend à partir des données", "Le temps mesuré principal"],
    ["Inférence (prédiction)", "Le modèle entraîné prédit sur de nouvelles données", "Mesurée sur le jeu de test"],
    ["Découpage train / test", "80 % des données pour apprendre, 20 % gardées de côté pour évaluer honnêtement",
     "Un seul découpage, commun aux deux outils"],
], [3.6, 7.4, 6.0])
h2("Les métriques de qualité")
table(["Métrique", "Ce qu'elle dit", "Lecture"], [
    ["R²", "Part de la variation des dépenses que le modèle explique", "1 = parfait, 0 = inutile. Ici 0,80 à 0,90"],
    ["RMSE", "Erreur moyenne, qui pénalise fortement les grosses erreurs",
     "En dollars ; plus c'est bas, mieux c'est (≈ 4 500 à 6 000 $)"],
    ["MAE", "Erreur moyenne en valeur absolue, plus facile à interpréter", "« En moyenne, on se trompe de X $ »"],
], [2.4, 7.6, 7.0])

h1("3. La préparation des données (pipeline Spark)")
table(["Concept", "Définition simple"], [
    ["Pipeline", "Une chaîne d'étapes appliquées toujours dans le même ordre, de la donnée brute au modèle"],
    ["StringIndexer", "Transforme un texte en numéro : southeast → 0, northwest → 1…"],
    ["OneHotEncoder", "Transforme ce numéro en colonnes 0/1 (une par valeur), pour que le modèle ne croie pas "
                      "que « région 3 » vaut plus que « région 1 »"],
    ["VectorAssembler", "Regroupe toutes les variables dans un seul vecteur features, le format attendu par Spark MLlib"],
    ["RegressionEvaluator", "Calcule RMSE, R² et MAE côté Spark"],
], [4.0, 13.0])
para("Côté scikit-learn, c'est l'équivalent avec ColumnTransformer + OneHotEncoder.", color=INK2)

h1("4. Les outils")
table(["Concept", "Définition simple"], [
    ["scikit-learn", "Bibliothèque Python de Machine Learning. Tout se passe en mémoire (RAM) sur une seule machine."],
    ["Apache Spark", "Moteur de calcul **distribué** : il découpe les données et le travail, puis les répartit."],
    ["PySpark", "L'interface Python de Spark (Spark est écrit en Scala et tourne sur la JVM)."],
    ["MLlib", "La bibliothèque de Machine Learning de Spark."],
    ["JVM", "La machine virtuelle Java dans laquelle tourne Spark. Elle met du temps à démarrer et réserve de "
            "la mémoire d'avance."],
    ["Docker / conteneur", "Une « mini-machine » isolée qui tourne sur votre PC ; on en a lancé 3 pour simuler un cluster."],
], [4.0, 13.0])

h1("5. Mono-nœud, distribué, cluster")
table(["Concept", "Définition simple", "Dans le projet"], [
    ["Nœud", "Une machine (ou un conteneur) qui participe au calcul", "Votre PC, ou chaque conteneur Docker"],
    ["Mono-nœud", "Tout le calcul se fait sur **une seule machine**", "scikit-learn sur votre PC"],
    ["Calcul distribué", "Le travail est découpé et réparti entre plusieurs cœurs ou machines", "Spark"],
    ["Cluster", "Un groupe de machines qui travaillent ensemble sous la direction d'un chef",
     "Master + 2 workers (Docker)"],
    ["Cœur (CPU core)", "Une unité de calcul du processeur ; chaque cœur fait une tâche à la fois",
     "Votre PC : 8 cœurs logiques"],
    ["Driver (pilote)", "Le programme principal : il lit le code, découpe le travail et récupère les résultats",
     "Notre script Python"],
    ["Master", "Le gestionnaire du cluster : il sait quels workers sont disponibles et leur attribue des ressources",
     "Conteneur master"],
    ["Worker", "Une machine du cluster qui offre ses cœurs et sa mémoire", "2 workers, 2 cœurs et 2 Go chacun"],
    ["Executor (exécuteur)", "Le processus qui fait réellement les calculs sur un worker", "1 exécuteur par worker, 1 Go"],
    ["local[*]", "Spark sur une seule machine, avec un seul processus qui utilise tous les cœurs (* = tous)",
     "Spark local, 8 cœurs"],
    ["Standalone", "Le gestionnaire de cluster intégré à Spark, le plus simple (il existe aussi YARN et Kubernetes)",
     "Notre cluster Docker"],
], [3.4, 8.0, 5.6])
h2("Les trois environnements comparés")
table(["", "scikit-learn", "Spark local[*]", "Spark cluster standalone"], [
    ["Machines", "1", "1", "1 physique, 3 conteneurs"],
    ["Organisation", "1 processus Python", "1 JVM, 8 cœurs", "Master + 2 workers, 4 cœurs"],
    ["Distribution", "Aucune", "Entre les cœurs", "Entre des exécuteurs séparés, via le réseau Docker"],
    ["Coût fixe", "Quasi nul", "≈ 2 s", "Un peu plus élevé"],
], [3.0, 4.0, 4.0, 6.0])

h1("6. Le fonctionnement de Spark")
table(["Concept", "Définition simple"], [
    ["Partition", "Un morceau des données. Spark découpe le jeu de données en partitions, et chaque partition est "
                  "traitée par une tâche."],
    ["Tâche (task)", "Le travail sur une partition ; une tâche occupe un cœur."],
    ["Job / Stage", "Un job est un calcul complet ; il se découpe en étapes (stages), séparées par des shuffles."],
    ["Évaluation paresseuse (lazy)", "Spark n'exécute rien tant qu'on ne demande pas un résultat. Les "
     "**transformations** (filter, select) sont seulement planifiées ; les **actions** (count, collect) déclenchent "
     "le calcul. C'est pour cela qu'on force les prédictions pour mesurer l'inférence."],
    ["Cache", "Garder les données en mémoire pour ne pas les relire du disque à chaque étape."],
    ["Shuffle", "Redistribuer les données entre partitions ou machines (par exemple pour regrouper ou agréger). "
                "C'est **l'opération la plus coûteuse** : écriture sur disque, sérialisation, transfert réseau."],
    ["Sérialisation", "Convertir des données en octets pour les envoyer à un autre processus ou une autre machine."],
    ["Parallélisme", "Faire plusieurs tâches en même temps. Avec 8 cœurs, 8 tâches au maximum en parallèle."],
    ["Coût fixe (overhead)", "Le temps perdu à organiser le travail, quelle que soit la taille des données : "
     "démarrage des jobs, planification des tâches, échanges. Environ 2 s ici."],
], [4.2, 12.8])
h2("Règle des partitions")
bullet("**Trop peu** (2 partitions pour 8 cœurs) : 6 cœurs ne font rien.")
bullet("**Trop** (32 partitions sur un petit volume) : beaucoup de petites tâches et plus de shuffle.")
bullet("**Idéal :** environ **une partition par cœur**, soit 8 ici.")

h1("7. Le vocabulaire du benchmark")
table(["Concept", "Définition simple", "Dans le projet"], [
    ["Benchmark", "Mesurer et comparer des performances dans des conditions contrôlées",
     "7 volumes × 4 partitions × 2 modèles × 3 répétitions"],
    ["Scalabilité", "Comment le temps évolue quand les données augmentent", "De 1 070 à 2,14 M lignes d'entraînement"],
    ["Seuil de basculement", "Le volume à partir duquel l'outil distribué devient plus rapide",
     "Entre x1000 et x2000 (1 à 2 M lignes), sur l'entraînement"],
    ["Temps total", "Lecture + préparation + entraînement + prédiction", "Spark reste un peu plus lent en temps total"],
    ["Réplication synthétique", "Copier les données avec un léger bruit pour simuler plus de volume", "x10 à x2000"],
    ["Fuite de données (data leakage)", "Quand des informations du test se retrouvent dans l'entraînement, ce qui "
     "fausse les scores", "Évitée : découpage fait **avant** la réplication"],
    ["Médiane de répétitions", "Lancer 3 fois et garder la valeur du milieu, moins sensible à un essai raté",
     "3 répétitions"],
    ["Échauffement (warm-up)", "Un premier lancement non compté, pour que la JVM et les bibliothèques soient chargées",
     "Fait des deux côtés"],
    ["RSS", "Mémoire réellement occupée par un processus", "Mesurée toutes les 50 ms"],
], [3.8, 7.4, 5.8])

h1("8. Les comparaisons faites")
table(["Comparaison", "Question posée", "Réponse"], [
    ["scikit-learn vs Spark local[*]", "Qui entraîne le plus vite selon le volume ?",
     "scikit-learn jusqu'à environ 1 M lignes ; Spark devient 1,2 à 1,3x plus rapide à 2,14 M"],
    ["Fit vs temps total", "Le gain de Spark tient-il en comptant tout ?",
     "Pas encore : en temps total, Spark reste 1,04 à 1,68x plus lent"],
    ["2 / 8 / 16 / 32 partitions", "Quel découpage est le meilleur ?", "Petit volume : 2. Grand volume : 8, une par cœur"],
    ["Précision des deux outils", "La qualité change-t-elle ?",
     "Régression Linéaire identique ; Random Forest légèrement différent (algorithme différent)"],
    ["Mémoire", "Qui consomme le plus ?", "Spark : environ 5 Go contre 1,5 Go, à cause de la JVM"],
    ["local[*] vs cluster", "Distribuer sur des workers aide-t-il ?",
     "Non sur une seule machine : 14 à 17 % plus lent (moins de cœurs, échanges réseau)"],
], [4.2, 5.0, 7.8])

h1("9. Questions probables du professeur")
h2("Sur la démarche")
qs = [
    ("Pourquoi avoir choisi ces deux modèles ?",
     "Un modèle simple et rapide (Régression Linéaire) et un modèle plus lourd en calcul (Random Forest). On voit "
     "ainsi l'effet de la complexité sur le seuil."),
    ("Pourquoi agrandir les données ? N'est-ce pas tricher ?",
     "1 338 lignes ne suffisent pas pour tester la scalabilité. La réplication mesure la **charge de calcul**, pas la "
     "qualité du modèle, et le rapport le précise."),
    ("Comment garantissez-vous une comparaison équitable ?",
     "Même découpage, mêmes variables, mêmes hyper-paramètres, échauffement, médiane de 3 répétitions."),
    ("Comment avez-vous évité la fuite de données ?",
     "Le découpage train/test est fait **avant** la réplication : toutes les copies d'une personne restent du même côté."),
]
k = 1
for q, a in qs:
    qa(k, q, a); k += 1
h2("Sur Spark et la distribution")
for q, a in [
    ("Pourquoi Spark est-il plus lent sur peu de données ?",
     "Le coût fixe (JVM, planification, tâches, shuffle) d'environ 2 s dépasse le temps de calcul utile."),
    ("Qu'est-ce qu'une partition ? Combien en choisir ?", "Un morceau des données traité par une tâche ; environ une par cœur."),
    ("Qu'est-ce que le shuffle et pourquoi coûte-t-il cher ?",
     "C'est la redistribution des données entre partitions : écriture, sérialisation, transfert."),
    ("Quelle différence entre driver, master, worker et executor ?",
     "Le driver est le programme et donne les ordres. Le master gère les ressources du cluster. Le worker est une "
     "machine du cluster. L'executor fait les calculs."),
    ("Qu'est-ce que l'évaluation paresseuse ?",
     "Spark planifie sans exécuter jusqu'à une action, d'où la nécessité de forcer les prédictions pour les chronométrer."),
    ("Est-ce un vrai cluster ?",
     "Un vrai ordonnanceur standalone avec des exécuteurs séparés, mais sur une seule machine physique. Il ne mesure "
     "donc pas le coût réseau entre machines."),
    ("Pourquoi le cluster est-il plus lent que local[*] ?",
     "4 cœurs au lieu de 8, et des échanges entre exécuteurs via le réseau Docker."),
]:
    qa(k, q, a); k += 1
h2("Sur les résultats")
for q, a in [
    ("Où est le seuil de basculement ?", "Entre 1 et 2 millions de lignes d'entraînement, pour l'entraînement seulement."),
    ("Pourquoi Spark reste-t-il plus lent en temps total ?",
     "La lecture du CSV, la préparation et le cache coûtent plus cher que chez pandas."),
    ("Pourquoi le R² du Random Forest diffère-t-il ?",
     "Spark découpe les variables continues en intervalles (maxBins = 32), alors que scikit-learn teste les seuils "
     "exacts : même réglage, algorithme différent."),
    ("Pourquoi Spark consomme-t-il plus de mémoire ?",
     "La JVM réserve sa mémoire d'avance, et Spark garde des copies en cache."),
]:
    qa(k, q, a); k += 1
h2("Sur les limites et la suite")
for q, a in [
    ("Que faudrait-il pour mesurer le vrai coût réseau ?",
     "Deux PC reliés en Ethernet, mêmes versions installées, données au même chemin sur chaque machine."),
    ("Quand utiliser Spark en entreprise ?",
     "Quand les données ne tiennent plus en RAM, quand elles sont déjà dans un environnement distribué (HDFS, data "
     "lake), ou quand on dispose de plusieurs machines."),
    ("Et si les données ne tenaient pas en mémoire ?",
     "scikit-learn échouerait ou devrait découper à la main ; Spark peut traiter des données plus grandes que la RAM "
     "d'une machine en les répartissant."),
    ("Que changeriez-vous si vous recommenciez ?",
     "Un vrai cluster multi-machines, mesurer la mémoire des exécuteurs, et un jeu de données réellement volumineux."),
]:
    qa(k, q, a); k += 1
h2("Questions pièges")
for q, a in [
    ("« Donc Spark est meilleur ? »",
     "Non : ça dépend du volume et de l'infrastructure. Sur une seule machine, scikit-learn reste le bon choix "
     "jusqu'à environ un million de lignes."),
    ("« Vos résultats valent-ils pour toutes les machines ? »",
     "Non : le seuil dépend du nombre de cœurs, de la RAM et du réseau. La méthode, elle, est reproductible."),
    ("« Pourquoi pas plus de partitions pour aller plus vite ? »",
     "Au-delà du nombre de cœurs, les tâches attendent leur tour et le shuffle augmente."),
]:
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(1); p.paragraph_format.keep_with_next = True
    r = p.add_run(q); r.bold = True; r.font.color.rgb = FOREST
    a_p = doc.add_paragraph(); a_p.paragraph_format.left_indent = Cm(0.6); a_p.paragraph_format.space_after = Pt(6)
    runs(a_p, a)

doc.core_properties.title = "Fiche de révision : Benchmark Scikit-Learn vs PySpark MLlib"
doc.save(OUT)
print(OUT)
