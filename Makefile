SHELL := /bin/bash

CLUSTER_NAME := cloud-assignment
VENV_PYTHON := .venv/bin/python
TRAINING_PYTHON := .venv-training/bin/python
TRAINING_STAMP := .venv-training/.installed
SERVICE_TEST_MARKER := .venv-training/.service-test-deps
SERVICE_IMAGE := cloud-assignment-service:local
MODEL_VERSION ?= v1
SUBSET ?=

.PHONY: cluster-up namespaces storage-up storage-bootstrap storage-status worker-image teacher-jobs clean-data task1-evidence test-worker test-training test-service service-image train evaluate-teacher evaluate-untrained evaluate-student evaluate-all quality-gate down

cluster-up:
	k3d cluster create --config cluster/k3d.yaml

namespaces:
	kubectl apply -f kubernetes/namespaces.yaml

storage-up: namespaces
	python3 scripts/apply_s3_secret.py
	kubectl apply -f kubernetes/seaweedfs.yaml
	kubectl -n data rollout status deployment/seaweedfs --timeout=300s

$(VENV_PYTHON): requirements-tools.txt
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -r requirements-tools.txt

storage-bootstrap: storage-up $(VENV_PYTHON)
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

task1-evidence: $(VENV_PYTHON)
	$(VENV_PYTHON) -m scripts.export_task1_evidence

test-worker:
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

service-image:
	docker build --file service/Dockerfile --tag $(SERVICE_IMAGE) .

train: $(TRAINING_STAMP)
	PYTHONUNBUFFERED=1 MODEL_VERSION=$(MODEL_VERSION) SUBSET=$(SUBSET) $(TRAINING_PYTHON) -m training.train

evaluate-teacher: $(TRAINING_STAMP)
	OLLAMA_URL=http://127.0.0.1:11434/api/generate $(TRAINING_PYTHON) -m training.evaluate --model teacher

evaluate-untrained: $(TRAINING_STAMP)
	$(TRAINING_PYTHON) -m training.evaluate --model untrained

evaluate-student: $(TRAINING_STAMP)
	$(TRAINING_PYTHON) -m training.evaluate --model student --version $(MODEL_VERSION)

evaluate-all: evaluate-teacher evaluate-untrained evaluate-student

quality-gate:
	python3 tools/score.py results/student_predictions.jsonl data/validation.jsonl --out results/student_validation.json --min-validity 95

down:
	k3d cluster delete $(CLUSTER_NAME)

