import unittest

from app.settings import settings


class SettingsTests(unittest.TestCase):
    def test_defaults_are_present(self):
        self.assertEqual(settings.api_key, "dev-api-key")
        self.assertEqual(settings.rate_limit_rpm, 60)
        self.assertEqual(settings.max_sync_texts, 64)


if __name__ == "__main__":
    unittest.main()
