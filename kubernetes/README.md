# Inference deployment

The deployment serves the selected `v2` model from `s3://models/v2`. Model
weights are downloaded and checksum-verified at pod startup; they are not baked
into the image or committed to Git.

The initial capacity settings are implementation assumptions chosen for the
local 8 GB M1 environment: two replicas, a 250 millicore CPU request, a 1 CPU
limit, a 512 MiB memory request, and a 1 GiB memory limit. The HPA maintains two
to four replicas and targets 60% average CPU utilization. Load-test results,
rather than these assumptions, are used for the final performance findings.

Build and deploy:

```bash
make service-deploy
kubectl -n app get deployment,pod,service,ingress,hpa,pdb
curl http://localhost:8080/readyz
```

The k3d load balancer maps host port 8080 to Traefik on port 80. The startup
probe allows up to five minutes for model download and initialization. Readiness
removes a pod from service until its model is available; liveness only checks
that the API process is alive.

Shutdown only the inference workload:

```bash
make service-down
```

Delete the complete local cluster with `make down` after all evidence has been
exported.
