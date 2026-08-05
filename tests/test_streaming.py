"""Tests for the SSE streaming translation endpoint."""
import json
import unittest

from tests.test_api import HEADERS, build_client


def parse_sse(text):
    """Parse a raw SSE body into a list of (event, data-dict)."""
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        events.append((event, data))
    return events


class StreamingTests(unittest.TestCase):
    def test_streams_one_event_per_sentence(self):
        client, _ = build_client()
        resp = client.post("/v1/translate/stream", headers=HEADERS, json={
            "source_lang": "en", "target_lang": "es",
            "text": "First sentence. Second sentence. Third one."})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers["content-type"])
        events = parse_sse(resp.text)

        data_events = [d for e, d in events if e == "message"]
        done = [d for e, d in events if e == "done"]
        self.assertEqual(len(data_events), 3)               # one per sentence
        self.assertEqual([d["index"] for d in data_events], [0, 1, 2])
        self.assertEqual(data_events[0]["text"], "FIRST SENTENCE.")  # fake pipe uppercases
        self.assertEqual(len(done), 1)                      # terminal done event

    def test_stream_auto_detect_emits_meta(self):
        client, _ = build_client()
        resp = client.post("/v1/translate/stream", headers=HEADERS, json={
            "source_lang": "auto", "target_lang": "es",
            "text": "This is clearly English text."})
        self.assertEqual(resp.status_code, 200)
        events = parse_sse(resp.text)
        meta = [d for e, d in events if e == "meta"]
        self.assertEqual(meta[0]["detected_source_lang"], "en")

    def test_stream_requires_auth(self):
        client, _ = build_client()
        resp = client.post("/v1/translate/stream", json={
            "source_lang": "en", "target_lang": "es", "text": "hi"})
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
