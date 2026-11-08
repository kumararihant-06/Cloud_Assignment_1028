SHELL := /bin/bash

CLUSTER_NAME := cloud-assignment
VENV_PYTHON := .venv/bin/python

.PHONY: cluster-up namespaces storage-up storage-bootstrap storage-status down

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

down:
	k3d cluster delete $(CLUSTER_NAME)

