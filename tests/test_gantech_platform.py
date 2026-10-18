"""Tests for the GAN-TECH platform client against a local fake platform (no network)."""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from app import gantech_platform as platform


class _FakePlatform(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *args):  # silence test output
        pass

    def _reply(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        _FakePlatform.calls.append(("GET", self.path, self.headers.get("Authorization")))
        if self.headers.get("Authorization") != "Bearer gt_live_test":
            return self._reply(401, {"error": {"code": "invalid_key", "message": "bad key"}})
        if "paid%40clinic.test" in self.path:
            return self._reply(
                200, {"data": {"access": True, "subscriptions": [{"plan": "Pro", "status": "active", "access": True}]}}
            )
        return self._reply(200, {"data": {"access": False, "subscriptions": []}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        _FakePlatform.calls.append(("POST", self.path, json.loads(self.rfile.read(length) or b"{}")))
        self._reply(201, {"data": {"id": 7, "status": "new"}})


class PlatformClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _FakePlatform)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.env = {
            "GANTECH_API_URL": f"http://127.0.0.1:{cls.server.server_port}/api/v1",
            "GANTECH_API_KEY": "gt_live_test",
            "GANTECH_PRODUCT": "test-product",
        }

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        platform.clear_cache()
        _FakePlatform.calls.clear()

    def test_off_until_configured(self):
        with mock.patch.dict(os.environ, {"GANTECH_API_URL": "", "GANTECH_API_KEY": "", "GANTECH_PRODUCT": ""}):
            self.assertFalse(platform.configured())
            self.assertTrue(platform.has_access("anyone@example.com"), "no gating when not configured")
            self.assertIsNone(platform.check_access("anyone@example.com"))
            self.assertIsNone(platform.forward_enquiry(name="A", email="a@b.co", message="Hello there"))
        self.assertEqual(_FakePlatform.calls, [])

    def test_access_answers_and_cache(self):
        with mock.patch.dict(os.environ, self.env):
            self.assertTrue(platform.has_access("Paid@Clinic.test"))
            self.assertTrue(platform.has_access("paid@clinic.test"))
            self.assertEqual(len(_FakePlatform.calls), 1, "answers are cached per person")
            self.assertIn("product=test-product", _FakePlatform.calls[0][1])
            self.assertFalse(platform.has_access("stranger@example.com"))
            self.assertFalse(platform.has_access("not-an-email"))

    def test_failure_modes(self):
        with mock.patch.dict(os.environ, {**self.env, "GANTECH_API_KEY": "gt_live_wrong"}):
            with self.assertRaises(platform.PlatformError) as caught:
                platform.check_access("paid@clinic.test")
            self.assertEqual(caught.exception.status, 401)
            self.assertTrue(platform.has_access("paid@clinic.test"), "fails open by default")
            with mock.patch.dict(os.environ, {"GANTECH_ACCESS_FAIL_MODE": "closed"}):
                platform.clear_cache()
                self.assertFalse(platform.has_access("paid@clinic.test"))

    def test_rejects_non_http_addresses(self):
        with (
            mock.patch.dict(os.environ, {**self.env, "GANTECH_API_URL": "file:///etc"}),
            self.assertRaises(platform.PlatformError),
        ):
            platform.check_access("paid@clinic.test")

    def test_forward_enquiry(self):
        with mock.patch.dict(os.environ, self.env):
            result = platform.forward_enquiry(name="Ama", email="ama@example.com", message="Please call me back.")
        self.assertEqual(result["data"]["status"], "new")
        method, path, body = _FakePlatform.calls[0]
        self.assertEqual((method, path), ("POST", "/api/v1/leads"))
        self.assertEqual(body["productName"], "test-product")
        self.assertTrue(body["consent"])


if __name__ == "__main__":
    unittest.main()
