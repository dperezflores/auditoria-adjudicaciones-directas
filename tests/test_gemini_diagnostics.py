"""Pruebas locales: consultar modelo no debe generar contenido."""
import unittest

from services.gemini_diagnostics import inspect_model


class StubClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.get_calls = []
        self.close_calls = 0
        self.models = self

    def get(self, *, model):
        self.get_calls.append(model)
        if self.error is not None:
            raise self.error
        return self.response

    def close(self):
        self.close_calls += 1


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__("Do not expose provider message or secrets")
        self.code = code


class DiagnosticTests(unittest.TestCase):
    def test_no_key_makes_no_request(self):
        made = []
        result = inspect_model("", "gemini-3.5-flash-lite", client_factory=lambda **kw: made.append(kw))
        self.assertFalse(result.available)
        self.assertEqual(result.code, "NO_KEY")
        self.assertEqual(made, [])

    def test_success_uses_only_get_not_generate_content(self):
        client = StubClient(response={"name": "models/gemini-3.5-flash-lite"})
        result = inspect_model(
            "test-key", "gemini-3.5-flash-lite",
            client_factory=lambda **kwargs: client,
        )
        self.assertTrue(result.available)
        self.assertEqual(result.code, "MODEL_VISIBLE")
        self.assertEqual(client.get_calls, ["gemini-3.5-flash-lite"])
        self.assertEqual(client.close_calls, 1)

    def test_401_sanitized(self):
        client = StubClient(error=FakeClientError(401))
        result = inspect_model("test-key", "gemini-model", client_factory=lambda **kwargs: client)
        self.assertFalse(result.available)
        self.assertEqual(result.http_code, 401)
        self.assertNotIn("Do not expose", result.description)
        self.assertEqual(client.close_calls, 1)

    def test_403_sanitized(self):
        result = inspect_model("test-key", "gemini-model",
                               client_factory=lambda **kwargs: StubClient(error=FakeClientError(403)))
        self.assertEqual(result.code, "HTTP_403")

    def test_404_sanitized(self):
        result = inspect_model("test-key", "gemini-model",
                               client_factory=lambda **kwargs: StubClient(error=FakeClientError(404)))
        self.assertEqual(result.code, "HTTP_404")

    def test_400_sanitized(self):
        result = inspect_model("test-key", "gemini-model",
                               client_factory=lambda **kwargs: StubClient(error=FakeClientError(400)))
        self.assertEqual(result.code, "HTTP_400")


if __name__ == "__main__":
    unittest.main()
