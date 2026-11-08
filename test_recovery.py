import os
import tempfile
import time
import threading
import unittest
import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask
from recovery_api import register_recovery
from lecture_ai import explain_interval


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"NEUROLEARN_DB": self.tmp.name + "/test.sqlite3"})
        self.env.start()
        self.app = Flask(__name__)
        register_recovery(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def save(self, **overrides):
        return self.client.post("/api/distractions", json={
            "id": "test-interval", "video_id": "abcdefghijk", "start": 10, "end": 20, **overrides})

    def wait_for(self, status):
        for _ in range(100):
            row = self.client.get("/api/distractions").json["items"][0]
            if row["status"] == status:
                return row
            time.sleep(.02)
        self.fail(f"Did not reach {status}: {row}")

    def test_validation_and_duplicate_delivery(self):
        for values in ({"start": -1}, {"end": 10}, {"end": 1900}, {"start": True}, {"video_id": "bad"}, {"end": float("nan")}):
            self.assertEqual(self.save(**values).status_code, 400)
        self.assertEqual(self.save().status_code, 201)
        self.save()
        self.assertEqual(len(self.client.get("/api/distractions").json["items"]), 1)

    def test_generation_and_persistence(self):
        self.save()
        with patch("recovery_api.explain_interval", return_value={"explanation": "Summary", "transcript": "[10s] source", "model": "fake"}):
            self.assertEqual(self.client.post("/api/distractions/test-interval/explain").status_code, 202)
            self.assertEqual(self.wait_for("complete")["explanation"], "Summary")
        another = Flask("reloaded")
        register_recovery(another)
        self.assertEqual(another.test_client().get("/api/distractions").json["items"][0]["transcript"], "[10s] source")

    def test_failure_is_retryable(self):
        self.save()
        with patch("recovery_api.explain_interval", side_effect=RuntimeError("No captions")):
            self.client.post("/api/distractions/test-interval/explain")
            self.assertEqual(self.wait_for("error")["error"], "No captions")
        with patch("recovery_api.explain_interval", return_value={"explanation": "Recovered", "transcript": "Source", "model": "fake"}):
            self.assertEqual(self.client.post("/api/distractions/test-interval/explain").status_code, 202)
            self.wait_for("complete")

    def test_unknown_interval(self):
        self.assertEqual(self.client.post("/api/distractions/missing/explain").status_code, 404)

    def test_clear_history_persists_and_allows_new_intervals(self):
        self.save()
        self.save(id="another", video_id="lmnopqrstuv")
        response = self.client.delete("/api/distractions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["deleted"], 2)
        another = Flask("cleared")
        register_recovery(another)
        self.assertEqual(another.test_client().get("/api/distractions").json["items"], [])
        self.assertEqual(self.client.delete("/api/distractions").json["deleted"], 0)
        self.assertEqual(self.save(id="new-session").status_code, 201)

    def test_clear_during_generation_does_not_restore_record(self):
        self.save()
        release = threading.Event()
        started = threading.Event()
        workers = []
        def delayed(*args):
            workers.append(threading.current_thread())
            started.set()
            release.wait(2)
            return {"explanation": "Done", "transcript": "Source", "model": "fake"}
        with patch("recovery_api.explain_interval", side_effect=delayed):
            self.client.post("/api/distractions/test-interval/explain")
            try:
                self.assertTrue(started.wait(1))
                self.assertEqual(self.client.delete("/api/distractions").json["deleted"], 1)
            finally:
                release.set()
                for worker in workers:
                    worker.join(3)
            self.assertEqual(self.client.get("/api/distractions").json["items"], [])

    def test_concurrent_request_is_busy(self):
        self.save()
        release = threading.Event()
        def delayed(*args):
            release.wait(2)
            return {"explanation": "Done", "transcript": "Source", "model": "fake"}
        with patch("recovery_api.explain_interval", side_effect=delayed):
            self.assertEqual(self.client.post("/api/distractions/test-interval/explain").status_code, 202)
            try:
                self.assertEqual(self.client.post("/api/distractions/test-interval/explain").status_code, 409)
            finally:
                release.set()
            self.wait_for("complete")


class CaptionTests(unittest.TestCase):
    def test_overlap_selection_and_ollama_payload(self):
        captions = [SimpleNamespace(start=0, duration=5, text="Excluded"),
                    SimpleNamespace(start=8, duration=4, text="Overlapping sentence"),
                    SimpleNamespace(start=15, duration=3, text="Inside"),
                    SimpleNamespace(start=20, duration=3, text="Excluded end")]
        with patch("youtube_transcript_api.YouTubeTranscriptApi.fetch", return_value=captions), \
             patch("lecture_ai.urlopen", return_value=io.BytesIO(json.dumps({"response": "Explanation"}).encode())) as call:
            result = explain_interval("abcdefghijk", 10, 20)
        self.assertIn("Overlapping sentence", result["transcript"])
        self.assertNotIn("Excluded", result["transcript"])
        payload = json.loads(call.call_args.args[0].data)
        self.assertFalse(payload["stream"])
        self.assertIn("Inside", payload["prompt"])

    def test_empty_captions_do_not_call_model(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi.fetch", return_value=[]), \
             patch("lecture_ai.urlopen") as call:
            with self.assertRaisesRegex(RuntimeError, "No captions overlap"):
                explain_interval("abcdefghijk", 10, 20)
            call.assert_not_called()

    def test_model_connection_failure(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi.fetch", return_value=[SimpleNamespace(start=10, duration=2, text="Source")]), \
             patch("lecture_ai.urlopen", side_effect=OSError("offline")):
            with self.assertRaisesRegex(RuntimeError, "Ollama is unavailable"):
                explain_interval("abcdefghijk", 10, 20)


if __name__ == "__main__":
    unittest.main()
