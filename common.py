"""Shared helpers: dataset scaling, memory sampling, Spark session setup."""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BASE_CSV = DATA_DIR / "insurance.csv"
SCALED_DIR = DATA_DIR / "scaled"
RESULTS_DIR = ROOT / "results"

CATEGORICAL = ["sex", "smoker", "region"]
NUMERIC = ["age", "bmi", "children"]
LABEL = "charges"
SEED = 42


def scaled_csv(factor: int) -> Path:
    """Create a shared, source-grouped split before replicating records.

    Exact duplicate originals share an ID. Synthetic copies never cross the split.
    These data measure workload scaling, not independent population growth.
    """
    if factor < 1:
        raise ValueError("scale must be positive")
    SCALED_DIR.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(BASE_CSV)
    base["source_id"] = pd.util.hash_pandas_object(base, index=False).astype(str)
    from sklearn.model_selection import train_test_split
    _, test_ids = train_test_split(np.asarray(base.source_id.unique()), test_size=0.2, random_state=SEED)
    base["split"] = np.where(base.source_id.isin(test_ids), "test", "train")
    out = SCALED_DIR / f"insurance_grouped_v2_x{factor}.csv"
    if out.exists():
        # Reuse only if the original data still match.
        old = pd.read_csv(out, usecols=["source_id"], dtype=str)
        if len(old) == len(base) * factor and set(old.source_id) == set(base.source_id):
            return out
    big = pd.concat([base] * factor, ignore_index=True)
    if factor > 1:
        rng = np.random.default_rng(SEED + factor)
        n = len(big)
        big["age"] = np.clip(big["age"] + rng.integers(-1, 2, n), 18, 64)
        big["bmi"] = (big["bmi"] * rng.normal(1.0, 0.02, n)).round(2)
        big["charges"] = (big["charges"] * rng.normal(1.0, 0.03, n)).round(4)
    big.to_csv(out, index=False)
    return out


class MemorySampler:
    """Samples RSS of this process + all children (incl. the Spark JVM) in a thread.

    Usage:  with MemorySampler() as m: ...;  m.peak_mb, m.delta_mb
    """

    def __init__(self, interval: float = 0.05):
        self.interval = interval
        self.proc = psutil.Process(os.getpid())
        self._stop = threading.Event()
        self.baseline_mb = 0.0
        self.peak_mb = 0.0

    def _rss(self) -> float:
        total = 0
        procs = [self.proc]
        try:
            procs += self.proc.children(recursive=True)
        except psutil.Error:
            pass
        for p in procs:
            try:
                total += p.memory_info().rss
            except psutil.Error:
                pass
        return total / 1024**2

    def _run(self):
        while not self._stop.is_set():
            self.peak_mb = max(self.peak_mb, self._rss())
            time.sleep(self.interval)

    def __enter__(self):
        self.baseline_mb = self._rss()
        self.peak_mb = self.baseline_mb
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        self.peak_mb = max(self.peak_mb, self._rss())

    @property
    def delta_mb(self) -> float:
        return self.peak_mb - self.baseline_mb


def get_spark(app_name: str = "InsuranceBenchmark", master: str = "local[*]",
              driver_memory: str = "4g"):
    """Create (or reuse) a SparkSession configured for Windows/local runs."""
    python_executable = sys.executable
    if os.name == "nt":
        import ctypes
        python_path = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(python_executable, python_path, 1024):
            python_executable = python_path.value
    os.environ.setdefault("PYSPARK_PYTHON", python_executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", python_executable)
    import pyspark
    # Use the Spark bundled with the pip package, not a system SPARK_HOME of another version.
    spark_home = os.path.dirname(pyspark.__file__)
    if os.name == "nt":  # Spark's .cmd launchers break on paths with spaces -> 8.3 short path
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(spark_home, buf, 1024):
            spark_home = buf.value
    os.environ["SPARK_HOME"] = spark_home
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.driver.memory", driver_memory)
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.sql.adaptive.enabled", "false")  # keep partition count as requested
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark
