# Mini-projet 08 — Benchmark ML : Scikit-Learn vs PySpark MLlib

A regression pipeline that predicts individual medical charges (`insurance.csv`), plus a
benchmark comparing single-node scikit-learn with distributed PySpark MLlib. It varies the
dataset size and the number of Spark partitions.

## Deliverables

| File | Role |
|---|---|
| `insurance_pipeline.py` | PySpark ML pipeline: `StringIndexer` + `OneHotEncoder` → `VectorAssembler` → `LinearRegression` / `RandomForestRegressor`, with RMSE / R² / MAE |
| `benchmark_sklearn_spark.py` | Automated benchmark: fit time, inference time, metrics, peak memory and shuffle bytes for partitions 2/8/16/32 at several data scales |
| `benchmark_report.pdf` | Generated report: summary tables, charts and the crossover analysis |
| `make_report.py` | Builds the PDF from `results/benchmark_results.csv` |
| `common.py` | Dataset scaling, memory sampler (Python + JVM RSS), SparkSession setup |

## Setup

Requires Java 17 (`JAVA_HOME`). On Windows it also needs `HADOOP_HOME` with `winutils.exe`.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

## Usage

```bash
# Single pipeline run
.venv/Scripts/python insurance_pipeline.py --model both --partitions 8 --scale 1

# Full benchmark (scales x1 to x2000, partitions 2 8 16 32), then the PDF
.venv/Scripts/python benchmark_sklearn_spark.py

# Quick smoke test
.venv/Scripts/python benchmark_sklearn_spark.py --quick

# Rebuild only the PDF from existing results
.venv/Scripts/python make_report.py
```

## Demo interface (for the presentation)

Double-click `lancer_demo.bat`, or run `.venv/Scripts/python demo/server.py`. The page opens at
http://localhost:8501. It uses the Python standard library only and works offline.

| Button | Duration | Writes to |
|---|---|---|
| Pipeline Spark | about 1 min | nothing (results shown on the page) |
| Effet des partitions | 2 to 3 min | `results/demo/` |
| Mini benchmark | about 4 min | `results/demo/` |
| Benchmark complet | about 1 h | `results/live/` |
| Cluster: start, mini benchmark, stop | 15 s / about 5 min / 10 s | `results/demo-cluster/` |

The demos never overwrite `results/benchmark_results.csv` or `results/cluster/`. Only one
experiment runs at a time. The cluster buttons need Docker Desktop to be running.

## Methodology notes

- A deterministic 80/20 split groups identical original records before replication.
  Both frameworks read the same `split` column; synthetic copies stay in that split.
- Scaled data simulate workload, not new independent patients. Accuracy at larger
  scales is not evidence of improved population generalization.
- RF shares tree count (20) and depth (5); implementation defaults and algorithms
  differ between libraries. Accuracy comparisons use the same held-out sources.
- Three repeats by default. Individual runs are saved in `benchmark_runs.csv`;
  summary CSV contains medians and timing standard deviations.
- `total_time_s` includes preparation, fit and prediction, but excludes CSV generation,
  Spark startup and evaluation. Fit includes pipeline preprocessing on both sides.
- Spark prediction values are consumed by a sum action to force evaluation.
- Shuffle is collected over the whole run (including evaluation). An unavailable
  Spark REST endpoint fails explicitly instead of recording a false zero.
- Memory is peak driver process-tree RSS, including the local JVM. Remote executors
  are excluded. The reused JVM and allocator can retain memory between runs.
- `local[*]` is a single-host experiment. The report labels execution mode and does
  not extrapolate crossover sizes beyond observed volumes.
- Use `--output-dir` for separate experiments. Defaults write the local CSVs to
  `results/` and the PDF to `benchmark_report.pdf`.

## Cluster experiments

See [CLUSTER.md](CLUSTER.md) for the included Docker master/two-worker setup,
a smoke test, a full run, and steps for a genuine multi-host experiment.
The Docker demonstration shares one physical machine and must be labelled as such.
When `results/cluster/benchmark_results.csv` exists, `make_report.py` adds a
section 9 to `benchmark_report.pdf` comparing local mode with the cluster, against scikit-learn
run in the same container with the same 4 cores.

## Verification

```powershell
.venv/Scripts/python -m unittest -v test_benchmark
```

