"""Automated benchmark: scikit-learn (single node) vs PySpark MLlib (distributed).

For every dataset scale factor and every model (Linear Regression, Random Forest):
  * scikit-learn : one run (in-memory pandas / numpy)
  * PySpark      : one run per partition count (default 2, 8, 16, 32)
Recorded: fit time, inference time, RMSE / R2 / MAE, peak RSS memory, Spark shuffle bytes.
Results -> results/benchmark_results.csv, then benchmark_report.pdf is generated.

    python benchmark_sklearn_spark.py                      # full grid
    python benchmark_sklearn_spark.py --quick              # fast smoke test
    python benchmark_sklearn_spark.py --scales 1 10 100 --partitions 4 8 --repeats 3
"""
from __future__ import annotations

import argparse
import os
import platform
from pathlib import Path
import statistics
import time

import numpy as np
import pandas as pd
import psutil
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from common import (CATEGORICAL, LABEL, NUMERIC, RESULTS_DIR, SEED, MemorySampler,
                    get_spark, scaled_csv)
from insurance_pipeline import RF_PARAMS, run_spark


# ---------------------------------------------------------------- scikit-learn side
def build_sklearn(model: str, n_jobs: int) -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", "passthrough", NUMERIC),
    ])
    if model == "lr":
        reg = LinearRegression()
    else:
        reg = RandomForestRegressor(n_estimators=RF_PARAMS["num_trees"],
                                    max_depth=RF_PARAMS["max_depth"],
                                    n_jobs=n_jobs, random_state=SEED)
    return Pipeline([("pre", pre), ("reg", reg)])


def run_sklearn(csv_path, model: str, n_jobs: int) -> dict:
    with MemorySampler() as mem:
        t0 = time.perf_counter()
        df = pd.read_csv(csv_path)
        train, test = df[df["split"] == "train"], df[df["split"] == "test"]
        X_tr, y_tr = train[NUMERIC + CATEGORICAL], train[LABEL]
        X_te, y_te = test[NUMERIC + CATEGORICAL], test[LABEL]
        prep_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        pipe = build_sklearn(model, n_jobs).fit(X_tr, y_tr)
        fit_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        pred = pipe.predict(X_te)
        inference_time = time.perf_counter() - t0

    return {
        "framework": "sklearn", "model": model, "partitions": 1,
        "n_train": len(X_tr), "n_test": len(X_te),
        "prep_time_s": prep_time, "fit_time_s": fit_time, "inference_time_s": inference_time,
        "total_time_s": prep_time + fit_time + inference_time,
        "rmse": float(np.sqrt(mean_squared_error(y_te, pred))),
        "r2": float(r2_score(y_te, pred)),
        "mae": float(mean_absolute_error(y_te, pred)),
        "peak_mem_mb": mem.peak_mb, "mem_delta_mb": mem.delta_mb,
        "shuffle_read_mb": 0.0, "shuffle_write_mb": 0.0,
    }


def median_run(fn, repeats: int, raw_rows=None, scale=None) -> dict:
    """Run `fn` `repeats` times; numeric fields = median across repeats."""
    runs = [fn() for _ in range(repeats)]
    if raw_rows is not None:
        raw_rows.extend(dict(r, repeat=i + 1, scale=scale) for i, r in enumerate(runs))
    out = dict(runs[0])
    for k, v in out.items():
        if isinstance(v, float):
            out[k] = statistics.median(r[k] for r in runs)
    for k in ("fit_time_s", "inference_time_s", "total_time_s"):
        out[k + "_std"] = statistics.stdev(r[k] for r in runs) if repeats > 1 else 0.0
    out["repeats"] = repeats
    return out


def log(r: dict, scale: int):
    print(f"  {r['framework']:7s} {r['model']:2s} x{scale:<4d} p={r['partitions']:<3d} "
          f"fit={r['fit_time_s']:7.2f}s inf={r['inference_time_s']:6.2f}s "
          f"R2={r['r2']:.4f} RMSE={r['rmse']:9.1f} mem={r['peak_mem_mb']:7.0f}MB "
          f"shuffleW={r['shuffle_write_mb']:7.2f}MB", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scales", type=int, nargs="+", default=[1, 10, 50, 200, 500, 1000, 2000],
                    help="dataset replication factors (1 = 1338 rows)")
    ap.add_argument("--partitions", type=int, nargs="+", default=[2, 8, 16, 32])
    ap.add_argument("--models", nargs="+", choices=["lr", "rf"], default=["lr", "rf"])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--sklearn-jobs", type=int, default=-1, help="n_jobs for sklearn RandomForest")
    ap.add_argument("--master", default="local[*]")
    ap.add_argument("--driver-memory", default="6g")
    ap.add_argument("--quick", action="store_true", help="scales 1 10, partitions 2 8, 1 repeat")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    ap.add_argument("--run-label", default="single-host")
    ap.add_argument("--spark-data-root", help="shared directory/URI containing generated CSV files")
    args = ap.parse_args()
    if args.quick:
        args.scales, args.partitions, args.repeats = [1, 10], [2, 8], 1

    if min(args.scales + args.partitions + [args.repeats]) < 1:
        ap.error("scales, partitions and repeats must be positive")
    if not args.master.startswith("local") and not args.spark_data_root:
        ap.error("cluster runs require --spark-data-root accessible to every worker")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    csvs = {s: scaled_csv(s) for s in args.scales}
    rows, raw_rows = [], []
    spark_csvs = {s: (args.spark_data_root.rstrip("/") + "/" + path.name
                      if args.spark_data_root else str(path)) for s, path in csvs.items()}

    # 1) scikit-learn first, so its RSS is not polluted by the Spark JVM.
    print("== scikit-learn (mono-noeud) ==")
    for m in args.models:  # warm-up (lazy imports, joblib pool), discarded
        run_sklearn(csvs[args.scales[0]], m, args.sklearn_jobs)
    for s in args.scales:
        for m in args.models:
            r = median_run(lambda: run_sklearn(csvs[s], m, args.sklearn_jobs), args.repeats, raw_rows, s)
            r["scale"] = s; rows.append(r); log(r, s)

    # 2) PySpark MLlib.
    print(f"== PySpark MLlib ({args.master}) ==")
    spark = get_spark("BenchmarkSklearnSpark", master=args.master,
                      driver_memory=args.driver_memory)
    env = {
        "spark_version": spark.version,
        "master": spark.sparkContext.master,
        "execution_mode": "local (single host)" if args.master.startswith("local") else "standalone/remote (verify worker hosts)",
        "memory_scope": "driver process tree RSS only; remote executors excluded",
        "run_label": args.run_label,
        "split_method": "source-grouped 80/20 before replication, seed 42",
        "synthetic_scaling": True,
        "default_parallelism": spark.sparkContext.defaultParallelism,
    }
    try:
        run_spark(spark, spark_csvs[args.scales[0]], "lr", 2)  # JVM / JIT warm-up, discarded
        for s in args.scales:
            for m in args.models:
                for p in args.partitions:
                    r = median_run(lambda: run_spark(spark, spark_csvs[s], m, p), args.repeats, raw_rows, s)
                    r["scale"] = s; rows.append(r); log(r, s)
    finally:
        spark.stop()

    df = pd.DataFrame(rows)
    out_csv = output_dir / "benchmark_results.csv"
    df.to_csv(out_csv, index=False)
    pd.DataFrame(raw_rows).to_csv(output_dir / "benchmark_runs.csv", index=False)

    import sklearn
    env.update({
        "python": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "sklearn_n_jobs": args.sklearn_jobs,
        "cpu": platform.processor() or platform.machine(),
        "logical_cores": os.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        "os": f"{platform.system()} {platform.release()}",
        "repeats": args.repeats,
        "date": time.strftime("%Y-%m-%d %H:%M"),
    })
    pd.Series(env).to_json(output_dir / "environment.json", indent=2)
    print(f"\nResults written to {out_csv}")

    if not args.no_report:
        from make_report import build_report
        report_path = Path("benchmark_report.pdf") if output_dir == RESULTS_DIR else output_dir / "benchmark_report.pdf"
        print(f"Report written to {build_report(out_csv, report_path)}")


if __name__ == "__main__":
    main()
