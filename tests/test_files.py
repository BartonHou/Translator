"""Tests for file parsing/serialization and the file-translation API flow."""
import json
import unittest

from app.core.files import detect_format, parse_file, serialize_file
from domain.models import TranslationJob
from tests.test_api import HEADERS, build_client


class FileParseTests(unittest.TestCase):
    def test_detect_format(self):
        self.assertEqual(detect_format("a.srt"), "srt")
        self.assertEqual(detect_format("README.md"), "md")
        with self.assertRaises(ValueError):
            detect_format("photo.png")

    def test_text_roundtrip_preserves_blank_lines(self):
        content = "First line.\n\nSecond line."
        segs, skel = parse_file(content, "txt")
        self.assertEqual(segs, ["First line.", "Second line."])
        rebuilt = serialize_file([s.upper() for s in segs], skel, "txt")
        self.assertEqual(rebuilt, "FIRST LINE.\n\nSECOND LINE.")

    def test_srt_preserves_indices_and_timestamps(self):
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHello world\n"
        segs, skel = parse_file(srt, "srt")
        self.assertEqual(segs, ["Hello world"])
        rebuilt = serialize_file(["Hola mundo"], skel, "srt")
        self.assertIn("00:00:01,000 --> 00:00:02,000", rebuilt)
        self.assertIn("Hola mundo", rebuilt)
        self.assertIn("1", rebuilt.split("\n")[0])


class FileApiTests(unittest.TestCase):
    def test_upload_creates_segmented_job(self):
        client, _ = build_client()
        from workers import tasks
        orig = tasks.translate_job_async.apply_async
        captured = {}
        tasks.translate_job_async.apply_async = lambda kwargs=None, queue=None: captured.update(kwargs or {})
        try:
            resp = client.post(
                "/v1/jobs/file",
                headers=HEADERS,
                data={"source_lang": "en", "target_lang": "es"},
                files={"file": ("doc.txt", b"Line one.\n\nLine two.", "text/plain")},
            )
        finally:
            tasks.translate_job_async.apply_async = orig
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["segments"], 2)
        self.assertEqual(captured["texts"], ["Line one.", "Line two."])

    def test_download_reassembles_translated_file(self):
        client, _ = build_client()
        from workers import tasks
        tasks.translate_job_async.apply_async = lambda kwargs=None, queue=None: None
        resp = client.post(
            "/v1/jobs/file",
            headers=HEADERS,
            data={"source_lang": "en", "target_lang": "es"},
            files={"file": ("doc.txt", b"Alpha.\n\nBeta.", "text/plain")},
        )
        job_id = resp.json()["job_id"]

        # Simulate the worker finishing the job.
        db = client.session_factory()
        job = db.get(TranslationJob, job_id)
        job.status = "SUCCEEDED"
        job.response_texts = json.dumps(["ALPHA.", "BETA."])
        db.commit()
        db.close()

        dl = client.get(f"/v1/jobs/{job_id}/download", headers=HEADERS)
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(dl.text, "ALPHA.\n\nBETA.")
        self.assertIn("attachment", dl.headers["content-disposition"])

    def test_unsupported_file_type_rejected(self):
        client, _ = build_client()
        resp = client.post(
            "/v1/jobs/file",
            headers=HEADERS,
            data={"source_lang": "en", "target_lang": "es"},
            files={"file": ("image.png", b"\x89PNG", "image/png")},
        )
        self.assertEqual(resp.status_code, 400)

    def test_download_not_ready_conflict(self):
        client, _ = build_client()
        from workers import tasks
        tasks.translate_job_async.apply_async = lambda kwargs=None, queue=None: None
        resp = client.post(
            "/v1/jobs/file",
            headers=HEADERS,
            data={"source_lang": "en", "target_lang": "es"},
            files={"file": ("doc.txt", b"Pending.", "text/plain")},
        )
        job_id = resp.json()["job_id"]
        dl = client.get(f"/v1/jobs/{job_id}/download", headers=HEADERS)
        self.assertEqual(dl.status_code, 409)  # still PENDING


if __name__ == "__main__":
    unittest.main()
