# Spark cluster setup

## Two-worker demonstration on this computer

Docker Desktop must be running with Linux containers. Allow at least 6 GB RAM
and 4 CPUs in Docker Desktop. Run these commands from the project directory:

```powershell
docker compose -f compose.spark.yaml build
docker compose -f compose.spark.yaml up -d master worker-1 worker-2
```

Open http://localhost:8080 and confirm **2 alive workers / 4 cores** before
starting a benchmark. This is a real standalone Spark scheduler with separate
executors, but all containers share one physical computer. Label results
`docker-single-host`; they do not demonstrate network costs across machines.

From Git Bash on Windows, run `export MSYS_NO_PATHCONV=1` first. Otherwise paths such as
`/workspace/data/scaled` are rewritten to Windows paths and Spark fails with
`No FileSystem for scheme "C"`. PowerShell is not affected.

Run a smoke experiment first:

```powershell
docker compose -f compose.spark.yaml run --rm benchmark python3 benchmark_sklearn_spark.py --master spark://master:7077 --spark-data-root /workspace/data/scaled --quick --sklearn-jobs 4 --output-dir results/cluster-smoke --run-label docker-single-host
```

Run the full experiment (both models, scales x1 to x1000, four partitions, three repeats; x2000 is left out because the executors have 1 GB):

```powershell
docker compose -f compose.spark.yaml run --rm benchmark
```

The Compose experiment assigns four executor cores in total and limits scikit-learn
and BLAS to four threads. Docker and Windows runs use different Python/library
versions; compare frameworks within each experiment.

Outputs go to `results/cluster/`, including a separate PDF. Local results remain
in `results/`. Do not run both benchmarks simultaneously. Stop the cluster when
finished:

```powershell
docker compose -f compose.spark.yaml down
```

The Compose ports are bound to localhost. Keep this demonstration cluster private.

## Multiple physical hosts (required to measure inter-machine network effects)

1. Use at least two Linux machines or VMs on different physical hosts, on a trusted
   private network. Install Java 17, Python, Spark 3.5.3, and this project's Python
   requirements on every node. Match Python minor versions across driver/workers.
2. Copy the project to each machine. Mount the same shared directory at the same
   absolute path on every machine, for example `/shared/insurance/data/scaled`.
3. On the driver, generate the exact shared inputs, then copy them to that mount:

   ```bash
   python3 -c "from common import scaled_csv; [scaled_csv(s) for s in [1,10,50,200,500]]"
   cp data/scaled/insurance_grouped_v2_*.csv /shared/insurance/data/scaled/
   ```

4. On the master host, replacing `MASTER_PRIVATE_IP` with its address:

   ```bash
   $SPARK_HOME/sbin/start-master.sh --host MASTER_PRIVATE_IP
   ```

5. On each worker host, start a worker. Adjust resources for each machine:

   ```bash
   $SPARK_HOME/sbin/start-worker.sh --cores 2 --memory 2g spark://MASTER_PRIVATE_IP:7077
   ```

6. Verify distinct host addresses in the master UI. Ensure workers can reach the
   driver's hostname and Spark ports on the private network. Execute on the driver:

   ```bash
   python3 benchmark_sklearn_spark.py --master spark://MASTER_PRIVATE_IP:7077 --spark-data-root /shared/insurance/data/scaled --driver-memory 2g --output-dir results/multi-host --run-label multi-host
   ```

7. Preserve the master UI worker list, machine specifications and Spark executor
   metrics alongside the generated results. The recorded RSS covers the driver
   process tree only: monitor remote executors separately before making claims
   about total cluster memory. Shuffle bytes include local and remote transfers;
   they alone do not measure network latency or establish a causal overhead threshold.

If no crossover occurs in the measured range, report that finding. A crossover
is not guaranteed and should never be invented or inferred from two data points.

References: [Spark 3.5.3 standalone setup](https://dlcdn.apache.org/spark/docs/3.5.3/spark-standalone.html)
and [cluster architecture](https://downloads.apache.org/spark/docs/3.5.3/cluster-overview.html).
