"""PySpark MLlib regression pipeline for individual medical charges (insurance.csv).

Pipeline:  StringIndexer -> OneHotEncoder (sex, smoker, region)
           -> VectorAssembler (dense features) -> LinearRegression | RandomForestRegressor
Metrics:   RMSE, R2, MAE (RegressionEvaluator)

Run standalone:
    python insurance_pipeline.py --model rf --partitions 8
    python insurance_pipeline.py --model both --scale 50 --partitions 16
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

from pyspark.ml import Pipeline
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.feature import OneHotEncoder, StringIndexer, VectorAssembler
from pyspark.ml.regression import LinearRegression, RandomForestRegressor
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import (DoubleType, IntegerType, StringType, StructField,
                               StructType)

from common import CATEGORICAL, LABEL, NUMERIC, SEED, MemorySampler, get_spark, scaled_csv

SCHEMA = StructType([
    StructField("age", IntegerType()),
    StructField("sex", StringType()),
    StructField("bmi", DoubleType()),
    StructField("children", IntegerType()),
    StructField("smoker", StringType()),
    StructField("region", StringType()),
    StructField("charges", DoubleType()),
    StructField("source_id", StringType()),
    StructField("split", StringType()),
])

# Same hyper-parameters are used on the scikit-learn side for a fair comparison.
RF_PARAMS = dict(num_trees=20, max_depth=5)


def build_pipeline(model: str) -> Pipeline:
    indexers = [StringIndexer(inputCol=c, outputCol=f"{c}_idx", handleInvalid="keep")
                for c in CATEGORICAL]
    encoder = OneHotEncoder(inputCols=[f"{c}_idx" for c in CATEGORICAL],
                            outputCols=[f"{c}_ohe" for c in CATEGORICAL])
    assembler = VectorAssembler(inputCols=NUMERIC + [f"{c}_ohe" for c in CATEGORICAL],
                                outputCol="features")
    if model == "lr":
        reg = LinearRegression(featuresCol="features", labelCol=LABEL)
    elif model == "rf":
        reg = RandomForestRegressor(featuresCol="features", labelCol=LABEL,
                                    numTrees=RF_PARAMS["num_trees"],
                                    maxDepth=RF_PARAMS["max_depth"], seed=SEED)
    else:
        raise ValueError(f"unknown model {model!r}")
    return Pipeline(stages=indexers + [encoder, assembler, reg])


def load_data(spark: SparkSession, path: str) -> DataFrame:
    return spark.read.csv(str(path), header=True, schema=SCHEMA)


def evaluate(predictions: DataFrame) -> dict:
    ev = RegressionEvaluator(labelCol=LABEL, predictionCol="prediction")
    return {m: ev.setMetricName(m).evaluate(predictions) for m in ("rmse", "r2", "mae")}


# ---------------------------------------------------------------- shuffle metrics
def _completed_stages(spark: SparkSession) -> dict:
    """Completed stages from the Spark REST API: {stage_id: (shuffle_read, shuffle_write)}."""
    sc = spark.sparkContext
    url = f"{sc.uiWebUrl}/api/v1/applications/{sc.applicationId}/stages?status=complete"
    last_exc = None
    for attempt in range(5):  # the UI can be slow right after start-up on a cluster
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                stages = json.load(r)
            break
        except Exception as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError("Spark shuffle metrics unavailable; check the Spark UI REST API") from last_exc
    return {(s["stageId"], s["attemptId"]): (s.get("shuffleReadBytes", 0),
                                             s.get("shuffleWriteBytes", 0)) for s in stages}


def shuffle_delta(before: dict, after: dict) -> tuple[int, int]:
    new = [v for k, v in after.items() if k not in before]
    return sum(v[0] for v in new), sum(v[1] for v in new)


# ---------------------------------------------------------------- one run
def run_spark(spark: SparkSession, csv_path, model: str, partitions: int) -> dict:
    """Train + evaluate one model with `partitions` partitions and return timings/metrics."""
    spark.conf.set("spark.sql.shuffle.partitions", str(partitions))
    stages_before = _completed_stages(spark)

    with MemorySampler() as mem:
        t0 = time.perf_counter()
        df = load_data(spark, csv_path)
        train, test = df.filter("split = 'train'"), df.filter("split = 'test'")
        train = train.repartition(partitions).cache()
        test = test.repartition(partitions).cache()
        n_train, n_test = train.count(), test.count()
        prep_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        fitted = build_pipeline(model).fit(train)
        fit_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        preds = fitted.transform(test)
        preds.selectExpr("sum(prediction)").collect()  # force prediction evaluation
        inference_time = time.perf_counter() - t0

    metrics = evaluate(preds)
    time.sleep(0.5)  # let the listener bus flush stage metrics to the REST API
    shuffle_read, shuffle_write = shuffle_delta(stages_before, _completed_stages(spark))
    train.unpersist(); test.unpersist()

    return {
        "framework": "spark", "model": model, "partitions": partitions,
        "n_train": n_train, "n_test": n_test,
        "prep_time_s": prep_time, "fit_time_s": fit_time, "inference_time_s": inference_time,
        "total_time_s": prep_time + fit_time + inference_time,
        **metrics,
        "peak_mem_mb": mem.peak_mb, "mem_delta_mb": mem.delta_mb,
        "shuffle_read_mb": shuffle_read / 1024**2, "shuffle_write_mb": shuffle_write / 1024**2,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model", choices=["lr", "rf", "both"], default="both")
    ap.add_argument("--partitions", type=int, default=8)
    ap.add_argument("--scale", type=int, default=1, help="dataset replication factor")
    ap.add_argument("--master", default="local[*]")
    ap.add_argument("--warmup", action="store_true",
                    help="discarded first run, so the JVM start-up is not counted in the timings")
    args = ap.parse_args()

    spark = get_spark("InsurancePipeline", master=args.master)
    csv = scaled_csv(args.scale)
    models = ["lr", "rf"] if args.model == "both" else [args.model]
    try:
        if args.warmup:
            print("Échauffement de la JVM (exécution non comptée)...", flush=True)
            run_spark(spark, csv, "lr", args.partitions)
        for m in models:
            r = run_spark(spark, csv, m, args.partitions)
            print(f"\n[{m.upper()}] rows train/test = {r['n_train']}/{r['n_test']}, "
                  f"partitions = {args.partitions}")
            print(f"  RMSE = {r['rmse']:.2f}   R2 = {r['r2']:.4f}   MAE = {r['mae']:.2f}")
            print(f"  fit = {r['fit_time_s']:.2f}s   inference = {r['inference_time_s']:.2f}s   "
                  f"shuffle W = {r['shuffle_write_mb']:.2f} MB   peak mem = {r['peak_mem_mb']:.0f} MB")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
