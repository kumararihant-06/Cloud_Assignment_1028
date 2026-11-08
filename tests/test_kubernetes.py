from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def resources(path):
    return [
        document
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if document
    ]


def resource_by_kind(documents, kind):
    return next(document for document in documents if document["kind"] == kind)


class KubernetesManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inference = resources(ROOT / "kubernetes" / "inference.yaml")
        cls.hpa = resource_by_kind(
            resources(ROOT / "kubernetes" / "hpa.yaml"),
            "HorizontalPodAutoscaler",
        )

    def test_selected_model_and_storage_endpoint_are_configured(self):
        config = resource_by_kind(self.inference, "ConfigMap")["data"]
        self.assertEqual(config["MODEL_URI"], "s3://models/v2")
        self.assertEqual(config["MODEL_VERSION"], "v2")
        self.assertEqual(config["TORCH_THREADS"], "1")
        self.assertIn("seaweedfs.data.svc.cluster.local", config["S3_ENDPOINT"])

    def test_deployment_has_replicas_probes_resources_and_secret_refs(self):
        deployment = resource_by_kind(self.inference, "Deployment")
        self.assertEqual(deployment["spec"]["replicas"], 2)
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertIn(probe, container)
        self.assertEqual(container["resources"]["limits"]["cpu"], "1")
        self.assertEqual(container["resources"]["limits"]["memory"], "1Gi")
        secret_names = {
            entry["valueFrom"]["secretKeyRef"]["name"]
            for entry in container["env"]
        }
        self.assertEqual(secret_names, {"s3-credentials"})

    def test_pod_and_container_security_are_restricted(self):
        deployment = resource_by_kind(self.inference, "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 10001)
        self.assertFalse(
            container["securityContext"]["allowPrivilegeEscalation"]
        )
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(
            container["securityContext"]["capabilities"]["drop"], ["ALL"]
        )

    def test_service_ingress_and_disruption_budget_exist(self):
        kinds = {document["kind"] for document in self.inference}
        self.assertTrue({"Service", "Ingress", "PodDisruptionBudget"} <= kinds)

    def test_hpa_targets_cpu_and_has_bounded_replica_count(self):
        spec = self.hpa["spec"]
        self.assertEqual(spec["minReplicas"], 2)
        self.assertEqual(spec["maxReplicas"], 4)
        self.assertEqual(
            spec["metrics"][0]["resource"]["target"]["averageUtilization"],
            60,
        )


if __name__ == "__main__":
    unittest.main()
