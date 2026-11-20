"""Interface de démonstration Streamlit : lancer les expériences et afficher les résultats.

    streamlit run app.py            puis ouvrir http://localhost:8501

Une seule expérience tourne à la fois ; les démos écrivent dans results/demo*/ et ne touchent
jamais aux résultats du benchmark complet.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(VENV_PY if VENV_PY.exists() else Path(sys.executable))

# Jeux de résultats affichables : clé -> (libellé, dossier)
DATASETS = {
    "local": ("Benchmark complet, local[*]", ROOT / "results"),
    "cluster": ("Benchmark complet, cluster Docker", ROOT / "results" / "cluster"),
    "live": ("Benchmark relancé avant la soutenance", ROOT / "results" / "live"),
    "demo": ("Dernière démo rapide (local)", ROOT / "results" / "demo"),
    "demo-cluster": ("Dernière démo rapide (cluster)", ROOT / "results" / "demo-cluster"),
}

COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.spark.yaml")]


def bench(*args):
    return [PY, "-u", str(ROOT / "benchmark_sklearn_spark.py"), *args]


TASKS = {
    "pipeline": {
        "cmd": [PY, "-u", str(ROOT / "insurance_pipeline.py"), "--model", "both", "--partitions", "8", "--warmup"],
        "label": "Pipeline Spark", "dur": "≈ 1 min", "dataset": None,
        "desc": "Entraîne la régression linéaire et la forêt aléatoire avec Spark (8 partitions) "
                "et affiche RMSE, R² et temps.",
    },
    "partitions": {
        "cmd": bench("--scales", "1", "200", "--partitions", "2", "8", "32", "--models", "rf",
                     "--repeats", "1", "--output-dir", "results/demo", "--no-report"),
        "label": "Effet des partitions", "dur": "≈ 2 à 3 min", "dataset": "demo",
        "desc": "Forêt aléatoire avec 2, 8 et 32 partitions, sur 1 070 puis 214 000 lignes, contre scikit-learn.",
    },
    "mini": {
        "cmd": bench("--quick", "--output-dir", "results/demo", "--no-report"),
        "label": "Mini benchmark", "dur": "≈ 4 min", "dataset": "demo",
        "desc": "Les deux modèles, volumes x1 et x10, 2 et 8 partitions : montre le coût fixe de Spark.",
    },
    "full": {
        "cmd": bench("--output-dir", "results/live", "--no-report"),
        "label": "Benchmark complet", "dur": "≈ 1 h · à lancer avant", "dataset": "live", "long": True,
        "desc": "Toute la grille, jusqu'à 2,14 millions de lignes (seuil de basculement). "
                "Résultats dans « Benchmark relancé ».",
    },
    "cluster-up": {
        "cmd": COMPOSE + ["up", "-d", "master", "worker-1", "worker-2"],
        "label": "Démarrer le cluster", "dur": "≈ 15 s", "dataset": None,
        "desc": "Lance le master et les deux workers. L'interface du master s'ouvre sur le port 8080.",
    },
    "cluster-mini": {
        "cmd": COMPOSE + ["run", "--rm", "benchmark", "python3", "-u", "benchmark_sklearn_spark.py",
                          "--master", "spark://master:7077", "--spark-data-root", "/workspace/data/scaled",
                          "--driver-memory", "2g", "--sklearn-jobs", "4", "--quick",
                          "--output-dir", "results/demo-cluster", "--run-label", "docker-single-host",
                          "--no-report"],
        "label": "Mini benchmark sur le cluster", "dur": "≈ 5 min", "dataset": "demo-cluster",
        "desc": "Même mini benchmark, exécuté par les deux workers (4 cœurs au total).",
    },
    "cluster-down": {
        "cmd": COMPOSE + ["down"], "label": "Arrêter le cluster", "dur": "≈ 10 s", "dataset": None,
        "desc": "Arrête et supprime les conteneurs du cluster.",
    },
}
LOCAL_TASKS = ["pipeline", "partitions", "mini", "full"]
CLUSTER_TASKS = ["cluster-up", "cluster-mini", "cluster-down"]

NOISE = ("WARN", "is not recognized as an internal", "operable program or batch file",
         "SUCCESS: The process", "setLogLevel", "Setting default log level")

NAME = {"lr": "Régression linéaire", "rf": "Random Forest"}
SK_COLOR, SP_COLOR, CL_COLOR = "#d95f02", "#1f6fb2", "#1b9e77"
RAMP = {2: "#a6c8ec", 8: "#5f9fdc", 16: "#1f6fb2", 32: "#0d3f6e"}


# ------------------------------------------------------------------ exécution en arrière-plan
class Job:
    """Un seul sous-processus à la fois, partagé entre les reruns et les onglets."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.task = None
        self.started = None
        self.ended = None
        self.code = None
        self.lines: list[str] = []
        self.stopped = False

    @property
    def running(self):
        return bool(self.proc and self.proc.poll() is None)

    def start(self, task):
        with self.lock:
            if self.running:
                return False, f"« {TASKS[self.task]['label']} » est déjà en cours."
            env = dict(os.environ, PYTHONIOENCODING="utf-8", MSYS_NO_PATHCONV="1")
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            try:
                self.proc = subprocess.Popen(TASKS[task]["cmd"], cwd=ROOT, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                             errors="replace", bufsize=1, env=env, creationflags=flags)
            except FileNotFoundError as exc:
                return False, f"Commande introuvable : {exc.filename}"
            self.task, self.started, self.ended, self.code, self.stopped = task, time.time(), None, None, False
            self.lines = [f"$ {TASKS[task]['label']}"]
            threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()
            return True, "ok"

    def _pump(self, proc):
        for line in proc.stdout:
            line = line.rstrip()
            if line and not any(n in line for n in NOISE):
                self.lines.append(line)
                if len(self.lines) > 2000:
                    del self.lines[:500]
        proc.wait()
        self.code, self.ended = proc.returncode, time.time()

    def stop(self):
        with self.lock:
            if not self.running:
                return False
            self.stopped = True
            if os.name == "nt":  # tue aussi la JVM enfant
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                self.proc.kill()
            return True

    @property
    def elapsed(self):
        return ((self.ended or time.time()) - self.started) if self.started else 0.0


@st.cache_resource
def get_job() -> Job:
    return Job()


# ------------------------------------------------------------------ données
def load_results(key):
    folder = DATASETS[key][1]
    f = folder / "benchmark_results.csv"
    if not f.exists():
        return None, {}, None
    df = pd.read_csv(f)
    env = {}
    if (folder / "environment.json").exists():
        env = json.loads((folder / "environment.json").read_text(encoding="utf-8"))
    return df, env, time.strftime("%d/%m %H:%M", time.localtime(f.stat().st_mtime))


def probe(url, timeout=0.6):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


@st.cache_data(ttl=4, show_spinner=False)
def environment_status():
    master = probe("http://127.0.0.1:8080/json/")
    app = probe("http://127.0.0.1:4040/api/v1/applications")
    return {"cluster_up": master is not None,
            "workers": master.get("aliveworkers", 0) if master else 0,
            "cores": master.get("cores", 0) if master else 0,
            "spark_ui": bool(app)}


PIPE_RE = re.compile(r"\[(LR|RF)\][^\n]*\n\s*RMSE = ([\d.]+)\s+R2 = ([\d.]+)\s+MAE = ([\d.]+)\n"
                     r"\s*fit = ([\d.]+)s\s+inference = ([\d.]+)s")


def fr(x, d=2):
    if x is None or pd.isna(x):
        return "–"
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def fr_int(x):
    return f"{round(x):,}".replace(",", " ")


def fmt_elapsed(s):
    m, sec = divmod(int(round(s)), 60)
    return f"{m} min {sec} s" if m else f"{sec} s"


# ------------------------------------------------------------------ page
st.set_page_config(page_title="Benchmark scikit-learn vs Spark", page_icon="📊", layout="wide")
job = get_job()

@st.fragment(run_every=5)
def environment_panel():
    envs = environment_status()
    st.markdown(f"{'🟢' if envs['spark_ui'] else '⚪'} [Interface Spark (4040)](http://localhost:4040)")
    cluster_txt = (f"Cluster : {envs['workers']} workers, {envs['cores']} cœurs"
                   if envs["cluster_up"] else "Cluster arrêté")
    st.markdown(f"{'🟢' if envs['cluster_up'] else '⚪'} [{cluster_txt}](http://localhost:8080)")


with st.sidebar:
    st.header("Environnement")
    environment_panel()
    pdfs = sorted((ROOT / "report").glob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
    if pdfs:
        st.download_button("Rapport PDF", pdfs[0].read_bytes(), file_name=pdfs[0].name,
                           mime="application/pdf", width="stretch")
    st.caption("Docker Desktop doit être ouvert pour les expériences sur le cluster.")

st.title("Benchmark ML : scikit-learn vs PySpark MLlib")
st.caption("Mini-projet 08 · interface de démonstration")


def task_card(key):
    t = TASKS[key]
    with st.container(border=True):
        st.markdown(f"**{t['label']}**")
        st.markdown(f":{'orange' if t.get('long') else 'green'}[{t['dur']}]")
        st.caption(t["desc"])
        confirmed = True
        if t.get("long"):
            confirmed = st.checkbox("Je confirme (≈ 1 h)", key=f"confirm-{key}", disabled=job.running)
        label = "Démarrer" if key == "cluster-up" else "Arrêter" if key == "cluster-down" else "Lancer"
        if st.button(label, key=f"run-{key}", disabled=job.running or not confirmed,
                     type="secondary" if key == "cluster-down" else "primary", width="stretch"):
            ok, msg = job.start(key)
            if not ok:
                st.error(msg)


@st.fragment(run_every=1.5)
def experiments():
    st.subheader("1. Lancer une expérience")
    st.caption("Une seule à la fois ; les démos n'écrasent pas les résultats du benchmark complet.")
    for col, key in zip(st.columns(len(LOCAL_TASKS)), LOCAL_TASKS):
        with col:
            task_card(key)

    st.markdown("##### Cluster Spark standalone")
    st.caption("Master + 2 workers sous Docker.")
    for col, key in zip(st.columns(len(CLUSTER_TASKS)), CLUSTER_TASKS):
        with col:
            task_card(key)

    st.subheader("2. Exécution en cours")
    with st.container(border=True):
        head, stop_col = st.columns([5, 1])
        if not job.task:
            head.markdown("Aucune exécution")
        else:
            label = TASKS[job.task]["label"]
            if job.running:
                state = f":blue[**En cours : {label}**]"
            elif job.stopped:
                state = f":red[**Arrêtée : {label}**]"
            elif job.code == 0:
                state = f":green[**Terminée : {label}**]"
            else:
                state = f":red[**Échec : {label} (code {job.code})**]"
            head.markdown(f"{state} · {fmt_elapsed(job.elapsed)}")
        if stop_col.button("Arrêter", key="stop", disabled=not job.running, width="stretch"):
            job.stop()
        log = "\n".join(job.lines[-400:]) if job.task else "Choisissez une expérience ci-dessus."
        st.code(log, language=None, height=260)

        if job.task == "pipeline":
            res = PIPE_RE.findall("\n".join(job.lines))
            if res:
                for col, (m, rmse, r2, mae, fit, inf) in zip(st.columns(len(res)), res):
                    col.metric(NAME[m.lower()], f"R² {fr(float(r2), 3)}")
                    col.caption(f"RMSE {fr_int(float(rmse))} \\$ · MAE {fr_int(float(mae))} \\$  \n"
                                f"fit {fr(float(fit))} s · prédiction {fr(float(inf))} s")

    # fin d'un benchmark : basculer l'affichage sur ses résultats
    if job.task and not job.running and job.code == 0:
        token = (job.task, job.started)
        if st.session_state.get("last_finished") != token:
            first_seen = "last_finished" not in st.session_state
            st.session_state.last_finished = token
            dataset = TASKS[job.task]["dataset"]
            if dataset and not first_seen:
                st.session_state.pending_dataset = dataset
                st.rerun(scope="app")
    elif "last_finished" not in st.session_state:
        st.session_state.last_finished = None


experiments()

# ------------------------------------------------------------------ résultats
st.subheader("3. Résultats")
available = [k for k, (_, folder) in DATASETS.items() if (folder / "benchmark_results.csv").exists()]
if not available:
    st.info("Pas encore de résultats.")
    st.stop()
if st.session_state.get("pending_dataset") in available:
    st.session_state.dataset = st.session_state.pop("pending_dataset")
if st.session_state.get("dataset") not in available:
    st.session_state.dataset = "local" if "local" in available else available[0]

key = st.selectbox("Jeu de résultats", available, format_func=lambda k: DATASETS[k][0], key="dataset")
df, env, modified = load_results(key)
st.caption(f"Mis à jour le {modified} · Spark {env.get('spark_version', '?')}, {env.get('master', '')} · "
           f"{env.get('repeats', '?')} répétition(s)")

models = [m for m in ("lr", "rf") if (df["model"] == m).any()]
scales = sorted(df["scale"].unique())
smax = scales[-1]
sk = df[df["framework"] == "sklearn"]
sp = df[df["framework"] == "spark"]


def sk_at(m, s):
    r = sk[(sk["model"] == m) & (sk["scale"] == s)]
    return r.iloc[0] if len(r) else None


def best_at(m, s):
    r = sp[(sp["model"] == m) & (sp["scale"] == s)]
    return r.loc[r["fit_time_s"].idxmin()] if len(r) else None


# tuiles
for m in models:
    tile_a, tile_b = st.columns(2)
    win = next((s for s in scales
                if sk_at(m, s) is not None and best_at(m, s) is not None
                and best_at(m, s)["fit_time_s"] < sk_at(m, s)["fit_time_s"]), None)
    a, b = sk_at(m, smax), best_at(m, smax)
    with tile_a.container(border=True):
        st.metric(f"{NAME[m]} : seuil de basculement", f"x{win}" if win else "non atteint")
        st.caption(f"≈ {fr_int(sk_at(m, win)['n_train'])} lignes d'entraînement" if win
                   else f"jusqu'à x{smax} ({fr_int(a['n_train'])} lignes)")
    with tile_b.container(border=True):
        if a is not None and b is not None:
            ratio = b["fit_time_s"] / a["fit_time_s"]
            txt = f"{fr(1 / ratio)}× plus rapide" if ratio < 1 else f"{fr(ratio)}× plus lent"
            st.metric(f"{NAME[m]} à x{smax}", txt)
            st.caption(f"Spark {fr(b['fit_time_s'])} s ({int(b['partitions'])} part.) "
                       f"contre scikit-learn {fr(a['fit_time_s'])} s")

c1, c2 = st.columns(2)

# 1. temps vs volume
with c1.container(border=True):
    st.markdown("**Temps d'entraînement selon le volume**")
    m_sel = st.segmented_control("Modèle", models, format_func=NAME.get, default=models[0],
                                 key="model_tab", label_visibility="collapsed") or models[0]
    sub = df[df["model"] == m_sel].copy()
    sub["série"] = sub.apply(lambda r: "scikit-learn" if r["framework"] == "sklearn"
                             else f"Spark, {int(r['partitions'])} partitions", axis=1)
    series = ["scikit-learn"] + [f"Spark, {p} partitions" for p in sorted(sp["partitions"].unique().astype(int))]
    colors = [SK_COLOR] + [RAMP.get(p, SP_COLOR) for p in sorted(sp["partitions"].unique().astype(int))]
    chart = alt.Chart(sub[sub["fit_time_s"] > 0]).mark_line(point=True).encode(
        x=alt.X("n_train:Q", scale=alt.Scale(type="log"), title="lignes d'entraînement"),
        y=alt.Y("fit_time_s:Q", scale=alt.Scale(type="log"), title="temps d'entraînement (s)"),
        color=alt.Color("série:N", scale=alt.Scale(domain=series, range=colors),
                        legend=alt.Legend(orient="bottom", title=None, columns=3)),
        tooltip=[alt.Tooltip("série:N"), alt.Tooltip("n_train:Q", title="lignes", format=",d"),
                 alt.Tooltip("fit_time_s:Q", title="fit (s)", format=".3f")],
    ).properties(height=320)
    st.altair_chart(chart, width="stretch")
    st.caption("Échelles logarithmiques. Survolez un point pour sa valeur.")

# 2. rapport Spark / sklearn
with c2.container(border=True):
    st.markdown("**Rapport temps Spark / temps scikit-learn**")
    rows = []
    for m in models:
        for s in scales:
            a, b = sk_at(m, s), best_at(m, s)
            if a is not None and b is not None and a["fit_time_s"] > 0:
                rows.append({"modèle": NAME[m], "n_train": a["n_train"],
                             "rapport": b["fit_time_s"] / a["fit_time_s"], "partitions": int(b["partitions"])})
    rdf = pd.DataFrame(rows)
    lines = alt.Chart(rdf).mark_line(point=True, strokeWidth=2.4).encode(
        x=alt.X("n_train:Q", scale=alt.Scale(type="log"), title="lignes d'entraînement"),
        y=alt.Y("rapport:Q", scale=alt.Scale(type="log"), title="Spark / scikit-learn"),
        color=alt.Color("modèle:N", scale=alt.Scale(domain=[NAME["lr"], NAME["rf"]], range=[SP_COLOR, CL_COLOR]),
                        legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["modèle", alt.Tooltip("n_train:Q", title="lignes", format=",d"),
                 alt.Tooltip("rapport:Q", format=".2f"), "partitions"],
    )
    rule = alt.Chart(pd.DataFrame({"y": [1]})).mark_rule(color="#9a9a96", strokeDash=[5, 4]).encode(y="y:Q")
    st.altair_chart((lines + rule).properties(height=360), width="stretch")
    st.caption("Sous la ligne pointillée, Spark est plus rapide. Meilleur nombre de partitions à chaque volume.")

c3, c4 = st.columns(2)

# 3. partitions
with c3.container(border=True):
    st.markdown("**Effet du nombre de partitions**")
    p_scale = st.selectbox("Volume", scales, index=len(scales) - 1,
                           format_func=lambda s: f"x{s} ({fr_int(sk_at(models[0], s)['n_train'])} lignes)",
                           key=f"pscale-{key}")
    for col, m in zip(st.columns(len(models)), models):
        bars = sp[(sp["model"] == m) & (sp["scale"] == p_scale)].sort_values("partitions").copy()
        if bars.empty:
            continue
        bars["partition"] = bars["partitions"].astype(int).astype(str) + " part."
        bars["meilleur"] = bars["fit_time_s"] == bars["fit_time_s"].min()
        ref = sk_at(m, p_scale)
        base = alt.Chart(bars).encode(x=alt.X("partition:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)))
        bar = base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            y=alt.Y("fit_time_s:Q", title="fit (s)"),
            color=alt.condition("datum.meilleur", alt.value("#1e7b3c"), alt.value(SP_COLOR)),
            tooltip=["partition", alt.Tooltip("fit_time_s:Q", title="fit (s)", format=".2f")],
        )
        text = base.mark_text(dy=-6, color="#8a8f87").encode(y="fit_time_s:Q", text=alt.Text("fit_time_s:Q", format=".1f"))
        layers = bar + text
        if ref is not None:
            layers += alt.Chart(pd.DataFrame({"y": [ref["fit_time_s"]]})).mark_rule(
                color=SK_COLOR, strokeWidth=2, strokeDash=[6, 4]).encode(y="y:Q")
        col.caption(NAME[m])
        col.altair_chart(layers.properties(height=240), width="stretch")
    st.caption("Barres : Spark (en vert, le meilleur). Trait orange : scikit-learn au même volume.")

# 4. tableau
with c4.container(border=True):
    st.markdown("**Valeurs mesurées**")
    table = []
    for s in scales:
        row = {"Volume": f"x{s}", "Lignes": fr_int(sk_at(models[0], s)["n_train"])}
        for m in models:
            a, b = sk_at(m, s), best_at(m, s)
            row[f"sklearn {m.upper()} (s)"] = fr(a["fit_time_s"], 3) if a is not None else "–"
            row[f"Spark {m.upper()} (s)"] = (f"{fr(b['fit_time_s'])} ({int(b['partitions'])})"
                                             + (" ✅" if a is not None and b["fit_time_s"] < a["fit_time_s"] else "")
                                             if b is not None else "–")
        for m in models:
            a, b = sk_at(m, s), best_at(m, s)
            row[f"R² {m.upper()} sk / Spark"] = (f"{fr(a['r2'], 3) if a is not None else '–'} / "
                                                 f"{fr(b['r2'], 3) if b is not None else '–'}")
        table.append(row)
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    st.caption("Temps d'entraînement médians, meilleure configuration Spark (nombre de partitions entre "
               "parenthèses). ✅ : Spark plus rapide.")
