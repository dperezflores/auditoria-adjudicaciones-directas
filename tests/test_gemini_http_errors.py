"""El diagnóstico HTTP no revela mensajes ni claves del proveedor."""
import unittest
from pathlib import Path

from services.gemini_errors import GeminiRequestError, safe_code, safe_status


class GeminiErrorTests(unittest.TestCase):
    def test_safe_400_and_guidance(self):
        exc = GeminiRequestError(400, "INVALID_ARGUMENT")
        self.assertEqual(exc.public_code, "HTTP_400_INVALID_ARGUMENT")
        self.assertIn("parámetros", exc.explanation)

    def test_free_tier_precondition(self):
        exc = GeminiRequestError(400, "FAILED_PRECONDITION")
        self.assertIn("facturación", exc.explanation)

    def test_429_limit(self):
        exc = GeminiRequestError(429, "RESOURCE_EXHAUSTED")
        self.assertIn("cuota", exc.explanation)

    def test_filters_untrusted_status(self):
        exc = GeminiRequestError(403, "sensitive raw details: secret key")
        self.assertEqual(exc.public_code, "HTTP_403_NO_STATUS")
        self.assertNotIn("sensitive", str(exc))

    def test_code_validation(self):
        self.assertIsNone(safe_code("my-secret"))
        self.assertEqual(safe_code("404"), 404)
        self.assertEqual(safe_status(""), "NO_STATUS")

    def test_do_not_override_gemini3_temperature(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "services" / "gemini_service.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("temperature=0", source)
        self.assertIn("response_json_schema=GEMINI_RESPONSE_SCHEMA_V2", source)
        self.assertNotIn("response_schema=ExtraccionContrato", source)


if __name__ == "__main__":
    unittest.main()
