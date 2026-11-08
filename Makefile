SHELL := /bin/bash

CLUSTER_NAME := cloud-assignment
VENV_PYTHON := .venv/bin/python
TRAINING_PYTHON := .venv-training/bin/python
MODEL_VERSION ?= v1
SUBSET ?=

.PHONY: cluster-up namespaces storage-up storage-bootstrap storage-status worker-image teacher-jobs clean-data test-worker test-training train down

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

test-worker:
	$(VENV_PYTHON) -m unittest -v tests.test_worker

$(TRAINING_PYTHON): requirements-training.txt
	python3 -m venv .venv-training
	$(TRAINING_PYTHON) -m pip install --upgrade pip
	$(TRAINING_PYTHON) -m pip install -r requirements-training.txt

test-training:
	$(VENV_PYTHON) -m unittest -v tests.test_training

train: $(TRAINING_PYTHON)
	MODEL_VERSION=$(MODEL_VERSION) SUBSET=$(SUBSET) $(TRAINING_PYTHON) -m training.train

down:
	k3d cluster delete $(CLUSTER_NAME)

