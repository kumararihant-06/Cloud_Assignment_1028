# Distilled Command Parser on Local Kubernetes

Cloud Computing assignment by **Arihant Kumar** (`230101028`).

- Repository: <https://github.com/kumararihant-06/Cloud_Assignment_1028>
- Model release: <https://github.com/kumararihant-06/Cloud_Assignment_1028/releases/tag/model-v2>
- Main report: [`report/report.pdf`](report/report.pdf)
- AI disclosure: [`AI_USE.md`](AI_USE.md)

This project labels 3,000 commands with Phi-3.5, cleans and stores the dataset in
SeaweedFS, distils it into Pythia-70M on CPU, and serves the selected v2 model
through FastAPI on k3d. Kubernetes provides probes, rolling updates, HPA,
ingress, resource controls, and pod-failure recovery.

## Architecture

```text
commands_pool.jsonl
  -> two deterministic Phi-3.5 labelling jobs
  -> SeaweedFS datasets bucket
  -> validation, deduplication and balancing
  -> CPU training (Pythia-70M v1 and v2)
  -> SeaweedFS models/v2 + GitHub Release
  -> FastAPI container (model downloaded and checksum-verified at startup)
  -> Kubernetes Service + Traefik ingress + HPA (2-4 replicas)
```

Model weights are excluded from Git by `.gitignore` and `.dockerignore`.
Credentials are generated directly into Kubernetes Secrets and are never
written to repository files.

## Measured results

| Result | Measured value |
|---|---:|
| Clean teacher examples | 2,798 / 3,000 |
| Clean dataset SHA-256 | `1331d0275bd00ee6066eccecf6d2e2c492dd1a51a522563d717ec3fbfeb5f2d8` |
| Selected student | v2 |
| V2 JSON validity | 99% |
| V2 intent / full-frame accuracy | 79% / 46% |
| Optimized load-test success | 95.12% (39/41) |
| Median / p95 latency | 8.1s / 26s |
| Throughput | 0.3437 requests/s |
| Single-pod recovery | 8s; 25/25 health probes passed |
| Cost at four replicas | ₹25.3194 / 1,000 successful requests |

The two load-test timeouts occurred during the initial HPA scale-up. See
`results/slo.json`, `results/loadtest_optimized_summary.txt`, and the report for
limitations and the distinction between measurements and assumptions.

## Prerequisites

- macOS or Linux with Git, Python, Make, Docker, `kubectl`, and `k3d`
- Ollama with `phi3.5` for regenerating teacher labels
- Approximately 5 GB free space for images, model cache, and cluster storage

Verified locally on macOS Tahoe 26.6.2, Apple M1 (8 cores), 8 GB RAM, Docker
Desktop, k3d 5.9.0, Kubernetes v1.35.5+k3s1, and Ollama 0.40.15.

## Setup and dataset pipeline

```bash
make cluster-up
make storage-bootstrap
```

In another terminal, expose Ollama to k3d and download the teacher:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
ollama pull phi3.5
```

Run the sharded labelling and cleaning jobs:

```bash
make teacher-jobs
kubectl -n pipeline wait --for=condition=complete job/teacher-worker-0 --timeout=2h
kubectl -n pipeline wait --for=condition=complete job/teacher-worker-1 --timeout=2h
make clean-data
kubectl -n pipeline wait --for=condition=complete job/clean-teacher-data --timeout=10m
make task1-evidence
```

The worker uses temperature `0`, seed `42`, a fixed JSON schema, two modulo
shards, and no validation labels. Cleaning rejects invalid records, keeps the
smallest ID for duplicate commands, and writes the checksum to `results/`.

## Training and evaluation

```bash
make train MODEL_VERSION=v1
make train MODEL_VERSION=v2
make evaluate-untrained
make evaluate-student MODEL_VERSION=v1
make evaluate-student MODEL_VERSION=v2
make evaluate-teacher       # Ollama must be running
make quality-gate MODEL_VERSION=v2
```

Training is CPU-only, target-token loss is masked from prompt tokens, and all
seeds and package versions are recorded in each model's `version.json`.
Artifacts are uploaded to `s3://models/<version>/` with SHA-256 verification.

## Tests, security and CI

```bash
.venv-training/bin/python -m unittest discover -s tests -v
python3 tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
make quality-gate MODEL_VERSION=v2
make cost-analysis
gitleaks git . --config .gitleaks.toml --redact
docker build --file service/Dockerfile --tag cloud-assignment-service:local .
```

GitHub Actions repeats the tests, quality gate, NACL simulation, cost
calculation, container build, and full-history secret scan. The verified run is
recorded in `results/ci.txt`.

## Build and deploy the inference service

```bash
make service-deploy
make service-status
curl http://localhost:8080/healthz
curl http://localhost:8080/readyz
curl -H 'Content-Type: application/json' \
  -d '{"text":"what is the weather in london"}' \
  http://localhost:8080/parse
```

Successful parse responses include `X-Model-Version` and `X-Served-By` headers.
The pod downloads `s3://models/v2`, verifies `model.sha256`, then becomes ready.
The image runs as UID 10001 with a read-only root filesystem and dropped Linux
capabilities.

## Load test and cost

The default target reproduces the supplied marking command:

```bash
make load-test
make cost-analysis
```

To preserve an earlier run, choose distinct output names:

```bash
make load-test \
  LOADTEST_PREFIX=results/loadtest_repeat \
  LOADTEST_HEADERS_OUT=results/loadtest_repeat_headers.json
```

All logs, predictions, evaluation reports, Locust CSVs, SLOs, cost output, and
reliability evidence are stored in `results/`.

## GitHub model release

Verify and stage the ignored v2 files:

```bash
make release-assets
```

Create the release after reviewing `dist/model-v2/SHA256SUMS`:

```bash
gh release create model-v2 dist/model-v2/* \
  --title "Distilled command parser v2" \
  --notes "Selected CPU-trained Pythia-70M model. See version.json and SHA256SUMS."
```

The assets include the trained model, tokenizer files, model configuration,
training loss, `version.json`, the original checksum manifest, and a release
`SHA256SUMS` file. Do not add `dist/` or `training/artifacts/` to Git.

## Shutdown

Remove only the inference workload:

```bash
make service-down
```

Export any remaining evidence first, then delete the complete local cluster:

```bash
make down
```

Deleting the cluster removes local Kubernetes workloads and PVC data. The
GitHub repository, Release assets, committed results, and final submission ZIP
are unaffected.
