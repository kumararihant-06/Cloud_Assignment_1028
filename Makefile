SHELL := /bin/bash

CLUSTER_NAME := cloud-assignment
VENV_PYTHON := .venv/bin/python
TOOLS_STAMP := .venv/.installed
TRAINING_PYTHON := .venv-training/bin/python
TRAINING_STAMP := .venv-training/.installed
SERVICE_TEST_MARKER := .venv-training/.service-test-deps
SERVICE_IMAGE := cloud-assignment-service:local
MODEL_VERSION ?= v1
SUBSET ?=
LOADTEST_PREFIX ?= results/loadtest
LOADTEST_HEADERS_OUT ?= results/loadtest_headers.json

.PHONY: cluster-up namespaces storage-up storage-bootstrap storage-status worker-image teacher-jobs clean-data task1-evidence test-worker test-training test-service test-kubernetes test-cost test-release service-image service-import service-deploy service-status service-down train evaluate-teacher evaluate-untrained evaluate-student evaluate-all quality-gate cost-analysis release-assets load-test down

cluster-up:
	k3d cluster create --config cluster/k3d.yaml

namespaces:
	kubectl apply -f kubernetes/namespaces.yaml

storage-up: namespaces
	python3 scripts/apply_s3_secret.py
	kubectl apply -f kubernetes/seaweedfs.yaml
	kubectl -n data rollout status deployment/seaweedfs --timeout=300s

$(TOOLS_STAMP): requirements-tools.txt
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -r requirements-tools.txt
	touch $(TOOLS_STAMP)

storage-bootstrap: storage-up $(TOOLS_STAMP)
	$(VENV_PYTHON) scripts/bootstrap_storage.py

storage-status:
	kubectl -n data get deployment,pod,service,pvc

worker-image:
	docker build --file worker/Dockerfile --tag cloud-assignment-worker:local .
	k3d image import cloud-assignment-worker:local --cluster $(CLUSTER_NAME)

teacher-jobs: worker-image
	kubectl -n pipeline delete job teacher-worker-0 teacher-worker-1 --ignore-not-found
	kubectl apply -f kubernetes/teacher-workers.yaml

clean-data:
	kubectl -n pipeline delete job clean-teacher-data --ignore-not-found
	kubectl apply -f kubernetes/clean-teacher-data.yaml

task1-evidence: $(TOOLS_STAMP)
	$(VENV_PYTHON) -m scripts.export_task1_evidence

test-worker: $(TOOLS_STAMP)
	$(VENV_PYTHON) -m unittest -v tests.test_worker

$(TRAINING_STAMP): requirements-training.txt
	python3 -m venv .venv-training
	$(TRAINING_PYTHON) -m pip install --upgrade pip
	$(TRAINING_PYTHON) -m pip install -r requirements-training.txt
	touch $(TRAINING_STAMP)

test-training: $(TRAINING_STAMP)
	$(TRAINING_PYTHON) -m unittest -v tests.test_training

$(SERVICE_TEST_MARKER): $(TRAINING_STAMP) requirements-test.txt service/requirements.txt
	$(TRAINING_PYTHON) -m pip install -r requirements-test.txt
	touch $(SERVICE_TEST_MARKER)

test-service: $(SERVICE_TEST_MARKER)
	$(TRAINING_PYTHON) -m unittest -v tests.test_service

test-kubernetes: $(TRAINING_STAMP)
	$(TRAINING_PYTHON) -m unittest -v tests.test_kubernetes

test-cost:
	python3 -m unittest -v tests.test_cost

test-release:
	python3 -m unittest -v tests.test_release

service-image:
	docker build --file service/Dockerfile --tag $(SERVICE_IMAGE) .

service-import: service-image
	k3d image import $(SERVICE_IMAGE) --cluster $(CLUSTER_NAME)

service-deploy: namespaces service-import
	python3 scripts/apply_s3_secret.py
	kubectl apply -f kubernetes/inference.yaml
	kubectl apply -f kubernetes/hpa.yaml
	kubectl -n app rollout restart deployment/command-parser
	kubectl -n app rollout status deployment/command-parser --timeout=300s

service-status:
	kubectl -n app get deployment,pod,service,ingress,hpa,pdb

service-down:
	kubectl delete -f kubernetes/hpa.yaml --ignore-not-found
	kubectl delete -f kubernetes/inference.yaml --ignore-not-found

train: $(TRAINING_STAMP)
	PYTHONUNBUFFERED=1 MODEL_VERSION=$(MODEL_VERSION) SUBSET=$(SUBSET) $(TRAINING_PYTHON) -m training.train

evaluate-teacher: $(TRAINING_STAMP)
	PYTHONUNBUFFERED=1 OLLAMA_URL=http://127.0.0.1:11434/api/generate $(TRAINING_PYTHON) -m training.evaluate --model teacher

evaluate-untrained: $(TRAINING_STAMP)
	PYTHONUNBUFFERED=1 $(TRAINING_PYTHON) -m training.evaluate --model untrained

evaluate-student: $(TRAINING_STAMP)
	PYTHONUNBUFFERED=1 $(TRAINING_PYTHON) -m training.evaluate --model student --version $(MODEL_VERSION)

evaluate-all: evaluate-teacher evaluate-untrained evaluate-student

quality-gate:
	python3 tools/score.py results/student_$(MODEL_VERSION)_predictions.jsonl data/validation.jsonl --out results/student_$(MODEL_VERSION)_validation.json --min-validity 95

cost-analysis:
	python3 -m scripts.cost

release-assets: $(TRAINING_STAMP)
	$(TRAINING_PYTHON) -m scripts.prepare_release --version v2

load-test: $(TOOLS_STAMP)
	LOADTEST_HEADERS_OUT=$(LOADTEST_HEADERS_OUT) $(VENV_PYTHON) -m locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv $(LOADTEST_PREFIX)

down:
	k3d cluster delete $(CLUSTER_NAME)

