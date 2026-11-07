import http.client
import json
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


class CspReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            cls.port = listener.getsockname()[1]
        cls.log = tempfile.TemporaryFile(mode="w+")
        cls.addClassCleanup(cls.log.close)
        receiver = Path(__file__).resolve().parents[2] / "images/f1-stats/csp-report.php"
        cls.server = subprocess.Popen(
            ["php", "-S", f"127.0.0.1:{cls.port}", str(receiver)],
            stdout=cls.log,
            stderr=cls.log,
        )
        cls.addClassCleanup(cls.stop_server)
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    return
            except OSError:
                if cls.server.poll() is not None:
                    break
                time.sleep(0.02)
        raise RuntimeError("PHP report receiver did not start")

    @classmethod
    def stop_server(cls):
        cls.server.terminate()
        cls.server.wait(timeout=5)

    def request(self, body, method="POST", content_type="application/csp-report"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, "/_csp/report", body, {"Content-Type": content_type})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            return response.status
        finally:
            connection.close()

    def events(self):
        self.log.seek(0)
        return [json.loads(line) for line in self.log.readlines() if line.startswith("{")]

    def test_report_discards_private_fields_and_keeps_one_json_event(self):
        before = len(self.events())
        report = {
            "effective-directive": "script-src-elem",
            "document-uri": "https://f1.example/private/person?token=secret#fragment",
            "blocked-uri": "https://user:password@cdn.example/script.js?token=secret",
            "source-file": "https://f1.example/private/script.js?secret=1",
            "line-number": 42,
            "column-number": 7,
            "referrer": "https://private.example/secret",
            "script-sample": "private code",
            "original-policy": "private policy",
            "unknown": "private extra",
        }
        self.assertEqual(self.request(json.dumps({"csp-report": report})), 204)
        events = self.events()
        self.assertEqual(len(events), before + 1)
        self.assertEqual(events[-1], {
            "level": "info", "event": "csp_violation", "disposition": "report",
            "directive": "script-src-elem", "document_origin": "https://f1.example",
            "blocked_origin": "https://cdn.example", "source_origin": "https://f1.example",
            "line_number": 42, "column_number": 7,
        })

    def test_invalid_reports_are_rejected_without_logging(self):
        before = len(self.events())
        for body in ["{", "null", "[]", '"string"', "1", "{}", '{"csp-report":[]}',
                     '{"csp-report":{"effective-directive":"script-src\\nprivate"}}',
                     '{"csp-report":{"effective-directive":["script-src"]}}']:
            with self.subTest(body=body):
                self.assertEqual(self.request(body), 400)
        self.assertEqual(len(self.events()), before)

    def test_body_method_and_media_type_limits(self):
        before = len(self.events())
        self.assertEqual(self.request("x" * 16385), 413)
        self.assertEqual(self.request("{}", method="GET"), 405)
        self.assertEqual(self.request("{}", content_type="text/plain"), 415)
        self.assertEqual(len(self.events()), before)

    def test_non_document_uris_and_enforcement_reports_are_rejected(self):
        before = len(self.events())
        for uri, disposition in [(None, "report"), ([], "report"), ("inline", "report"),
                                 ("https://f1.example", "enforce")]:
            report = {"effective-directive": "script-src", "document-uri": uri,
                      "disposition": disposition}
            self.assertEqual(self.request(json.dumps({"csp-report": report})), 400)
        self.assertEqual(len(self.events()), before)

    def test_special_uris_and_malformed_fields_cannot_leak_payloads(self):
        for uri, expected in [("inline", "inline"), ("eval", "eval"),
                              ("data:text/plain,secret", "data:"),
                              ("blob:https://private.example/secret", "blob:"),
                              ("javascript:secret", None), ({"secret": "value"}, None)]:
            with self.subTest(uri=uri):
                report = {"effective-directive": "script-src", "blocked-uri": uri,
                          "document-uri": "https://f1.example", "source-file": 1,
                          "line-number": "secret", "column-number": -1}
                self.assertEqual(self.request(json.dumps({"csp-report": report})), 204)
                event = self.events()[-1]
                self.assertEqual(event["blocked_origin"], expected)
                self.assertEqual(event["document_origin"], "https://f1.example")
                self.assertIsNone(event["source_origin"])
                self.assertNotIn("line_number", event)
                self.assertNotIn("column_number", event)


if __name__ == "__main__":
    unittest.main()
