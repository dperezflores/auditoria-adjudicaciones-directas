"""Pruebas aisladas de autorización; no realizan conexiones con Google."""
import unittest

from security.app_access import configuration_status, is_authorized_identity


def complete_settings():
    return {
        "auth": {
            "redirect_uri": "https://example.test/oauth2callback",
            "cookie_secret": "test-only-not-a-real-secret",
            "client_id": "example-client",
            "client_secret": "test-secret",
            "server_metadata_url":
                "https://accounts.google.com/.well-known/openid-configuration",
        },
        "access": {"allowed_emails": ["AUDITOR@example.test"]},
    }


class AppAccessTests(unittest.TestCase):
    def test_without_secrets_is_demo(self):
        self.assertEqual(configuration_status({}), "demo")

    def test_partial_auth_blocks(self):
        self.assertEqual(configuration_status({"auth": {"client_id": "x"}}), "incomplete")

    def test_missing_allowed_emails_blocks(self):
        settings = complete_settings()
        settings.pop("access")
        self.assertEqual(configuration_status(settings), "incomplete")

    def test_complete_config_enables_login(self):
        self.assertEqual(configuration_status(complete_settings()), "enabled")

    def test_verified_allowed_identity(self):
        self.assertTrue(is_authorized_identity(
            {"email": "auditor@EXAMPLE.test", "email_verified": True},
            ["AUDITOR@example.test"],
        ))

    def test_reject_unverified_email(self):
        self.assertFalse(is_authorized_identity(
            {"email": "auditor@example.test", "email_verified": False},
            ["auditor@example.test"],
        ))

    def test_reject_unknown_email(self):
        self.assertFalse(is_authorized_identity(
            {"email": "other@example.test", "email_verified": True},
            ["auditor@example.test"],
        ))


if __name__ == "__main__":
    unittest.main()
