import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from service.app import create_app
from service.runtime import Settings, model_location
from service.schema import InvalidModelOutput, first_json_object, validated_output


VALID = '{"intent":"weather_query","date":null,"time":null,"place":"london"}'


class FakeRuntime:
    ready = True
    load_error = None

    def __init__(self, output=VALID):
        self.output = output

    def generate(self, text, max_new_tokens):
        return self.output


def settings(fault=False):
    return Settings(
        model_uri="s3://models/v1",
        model_version="v1",
        s3_endpoint="http://seaweedfs:8333",
        max_new_tokens=96,
        fault_inject=fault,
    )


class SchemaTests(unittest.TestCase):
    def test_extracts_first_balanced_json_object(self):
        self.assertEqual(first_json_object(f"prefix {VALID} suffix"), VALID)
        self.assertEqual(validated_output(f"prefix {VALID} suffix")["place"], "london")

    def test_rejects_wrong_keys_and_invalid_values(self):
        with self.assertRaises(InvalidModelOutput):
            validated_output('{"intent":"weather_query"}')
        with self.assertRaises(InvalidModelOutput):
            validated_output(
                '{"intent":"weather_query","date":3,"time":null,"place":null}'
            )

    def test_model_uri_parser(self):
        self.assertEqual(model_location("s3://models/v1/"), ("models", "v1"))


class EndpointTests(unittest.TestCase):
    def test_health_and_readiness(self):
        client = TestClient(create_app(FakeRuntime(), settings(), start_loader=False))
        self.assertEqual(client.get("/healthz").status_code, 200)
        self.assertEqual(client.get("/readyz").status_code, 200)

    def test_parse_returns_exact_body_and_headers(self):
        with patch.dict(os.environ, {"HOSTNAME": "pod-1"}):
            client = TestClient(create_app(FakeRuntime(), settings(), start_loader=False))
            response = client.post("/parse", json={"text": "weather in london"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "weather_query")
        self.assertEqual(set(response.json()), {"intent", "date", "time", "place"})
        self.assertEqual(response.headers["X-Model-Version"], "v1")
        self.assertEqual(response.headers["X-Served-By"], "pod-1")

    def test_fault_injection_returns_exact_error(self):
        client = TestClient(create_app(FakeRuntime(), settings(True), start_loader=False))
        response = client.post("/parse", json={"text": "weather in london"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "invalid_model_output"})

    def test_not_ready_returns_503(self):
        runtime = FakeRuntime()
        runtime.ready = False
        client = TestClient(create_app(runtime, settings(), start_loader=False))
        self.assertEqual(client.get("/readyz").status_code, 503)
        self.assertEqual(client.post("/parse", json={"text": "x"}).status_code, 503)


if __name__ == "__main__":
    unittest.main()

