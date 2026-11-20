"""Interface de démonstration locale : lancer les expériences et afficher les résultats.

    python demo/server.py            puis ouvrir http://localhost:8501

Bibliothèque standard uniquement (aucune installation). Une seule expérience tourne à la fois ;
les démos écrivent dans results/demo*/ et ne touchent jamais aux résultats du benchmark complet.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("DEMO_PORT", "8501"))
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
        "label": "Pipeline Spark, 2 modèles", "dataset": None,
    },
    "partitions": {
        "cmd": bench("--scales", "1", "200", "--partitions", "2", "8", "32", "--models", "rf",
                     "--repeats", "1", "--output-dir", "results/demo", "--no-report"),
        "label": "Effet des partitions (Random Forest)", "dataset": "demo",
    },
    "mini": {
        "cmd": bench("--quick", "--output-dir", "results/demo", "--no-report"),
        "label": "Mini benchmark", "dataset": "demo",
    },
    "full": {
        "cmd": bench("--output-dir", "results/live", "--no-report"),
        "label": "Benchmark complet (x1 à x2000)", "dataset": "live",
    },
    "cluster-up": {
        "cmd": COMPOSE + ["up", "-d", "master", "worker-1", "worker-2"],
        "label": "Démarrage du cluster", "dataset": None,
    },
    "cluster-down": {
        "cmd": COMPOSE + ["down"], "label": "Arrêt du cluster", "dataset": None,
    },
    "cluster-mini": {
        "cmd": COMPOSE + ["run", "--rm", "benchmark", "python3", "-u", "benchmark_sklearn_spark.py",
                          "--master", "spark://master:7077", "--spark-data-root", "/workspace/data/scaled",
                          "--driver-memory", "2g", "--sklearn-jobs", "4", "--quick",
                          "--output-dir", "results/demo-cluster", "--run-label", "docker-single-host",
                          "--no-report"],
        "label": "Mini benchmark sur le cluster", "dataset": "demo-cluster",
    },
}

NOISE = ("WARN", "is not recognized as an internal", "operable program or batch file",
         "SUCCESS: The process", "setLogLevel", "Setting default log level")


class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.task = None
        self.started = None
        self.ended = None
        self.code = None
        self.lines: list[str] = []
        self.stopped = False

    def start(self, task):
        with self.lock:
            if self.proc and self.proc.poll() is None:
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
            threading.Thread(target=self._pump, daemon=True).start()
            return True, "ok"

    def _pump(self):
        proc = self.proc
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
            if self.proc and self.proc.poll() is None:
                self.stopped = True
                if os.name == "nt":  # tue aussi la JVM enfant
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                                   capture_output=True)
                else:
                    self.proc.kill()
                return True
            return False

    def status(self):
        running = bool(self.proc and self.proc.poll() is None)
        now = time.time()
        return {
            "task": self.task, "label": TASKS[self.task]["label"] if self.task else None,
            "dataset": TASKS[self.task]["dataset"] if self.task else None,
            "running": running, "code": self.code, "stopped": self.stopped,
            "elapsed": round(((self.ended or now) - self.started), 1) if self.started else 0,
            "lines": self.lines[-400:],
        }


JOB = Job()


def read_results(key):
    label, folder = DATASETS[key]
    f = folder / "benchmark_results.csv"
    if not f.exists():
        return {"key": key, "label": label, "available": False}
    with open(f, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    num = lambda v: float(v) if v not in ("", None) else None
    out = [{k: (v if k in ("framework", "model") else num(v)) for k, v in r.items()} for r in rows]
    env = {}
    if (folder / "environment.json").exists():
        env = json.loads((folder / "environment.json").read_text(encoding="utf-8"))
    return {"key": key, "label": label, "available": True, "rows": out, "env": env,
            "modified": time.strftime("%d/%m %H:%M", time.localtime(f.stat().st_mtime))}


def probe(url, timeout=1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send((HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/datasets":
            return self._send([{"key": k, "label": v[0],
                                "available": (v[1] / "benchmark_results.csv").exists()}
                               for k, v in DATASETS.items()])
        if path.startswith("/api/results/"):
            key = path.rsplit("/", 1)[-1]
            return self._send(read_results(key) if key in DATASETS else {"error": "inconnu"},
                              code=200 if key in DATASETS else 404)
        if path == "/api/status":
            return self._send(JOB.status())
        if path == "/api/env":
            master = probe("http://127.0.0.1:8080/json/")
            app = probe("http://127.0.0.1:4040/api/v1/applications", 0.8)
            return self._send({
                "cluster": {"up": master is not None,
                            "workers": master.get("aliveworkers") if master else 0,
                            "cores": master.get("cores") if master else 0},
                "sparkUi": bool(app),
            })
        if path == "/rapport.pdf" and (ROOT / "report" / "main.pdf").exists():
            return self._send((ROOT / "report" / "main.pdf").read_bytes(), "application/pdf")
        return self._send({"error": "introuvable"}, code=404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/run/"):
            task = path.rsplit("/", 1)[-1]
            if task not in TASKS:
                return self._send({"ok": False, "message": "tâche inconnue"}, code=404)
            ok, msg = JOB.start(task)
            return self._send({"ok": ok, "message": msg}, code=200 if ok else 409)
        if path == "/api/stop":
            return self._send({"ok": JOB.stop()})
        return self._send({"error": "introuvable"}, code=404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Interface de démonstration : {url}  (Ctrl+C pour arrêter)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        JOB.stop()


if __name__ == "__main__":
    main()
