"""Retry-After parsing/transport: safe normalized data, never automatic retries."""

from email.message import Message
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from metadata_http import HTTPPolicy, HTTPResult, MetadataHTTPError, MetadataResponseError, get_metadata_json
from retry_after import RetryAfter, parse_retry_after


URL = "https://metadata.example.test/models"
POLICY = HTTPPolicy(frozenset({"metadata.example.test"}), 1000, 20)


class RetryAfterTests(unittest.TestCase):
    def setUp(self):
        for target in ("time.sleep", "socket.create_connection", "socket.socket.connect", "socket.getaddrinfo"):
            guard = patch(target, side_effect=AssertionError("Real network/wait forbidden"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_seconds_zero_padding_and_extremes_do_not_overflow(self):
        for raw, expected in (("0", 0), (" 0007 ", 7), ("0" * 5000 + "7", 7),
                              ("999999999999999999", 999999999999999999)):
            with self.subTest(raw=raw[:20]):
                self.assertEqual(parse_retry_after(raw), RetryAfter(seconds=expected))
        self.assertEqual(parse_retry_after("9" * 5000), RetryAfter(excessive=True))

    def test_http_dates_are_normalized_without_reading_a_wall_clock(self):
        parsed = parse_retry_after("Tue, 27 Oct 2026 12:00:07 GMT")
        self.assertIsInstance(parsed, RetryAfter)
        self.assertIsNone(parsed.seconds)
        self.assertGreater(parsed.not_before, 0)
        self.assertIsNotNone(parse_retry_after("Fri, 31 Dec 9999 23:59:59 GMT"))
        self.assertIsNotNone(parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT"))
        self.assertEqual(parse_retry_after("Tue Oct 27 12:00:07 2026"), parsed)
        self.assertEqual(parse_retry_after("Tuesday, 27-Oct-26 12:00:07 GMT"),
                         RetryAfter(legacy_date=(26, 10, 27, 12, 0, 7, 1)))
        self.assertEqual(parse_retry_after("Sun Nov  6 08:49:37 1994"), parse_retry_after("Sun, 06 Nov 1994 08:49:37 GMT"))

    def test_missing_invalid_dates_and_non_ascii_numbers_are_ignored(self):
        for value in (None, 7, True, {}, "", "1.5", "-1", "+7", "７", "NaN", "Infinity",
                      "Wed, 27 Oct 2026 12:00:00 GMT", "Tue, 99 Oct 2026 12:00:00 GMT",
                      "Tue, 27 Oct 2026 12:00:00", "Tue, 27 Oct 2026 12:00:00 +0100",
                      "Tue, 27 Oct 2026 25:00:00 GMT", "SYNTHETIC-CREDENTIAL", "7\r\nSet-Cookie: SYNTHETIC"):
            with self.subTest(value=value):
                self.assertIsNone(parse_retry_after(value))

    def test_normalized_type_rejects_ambiguous_or_invalid_values(self):
        for args in ({}, {"seconds": -1}, {"seconds": True}, {"seconds": 10**18},
                     {"seconds": 7, "not_before": 1}, {"seconds": 7, "excessive": True},
                     {"not_before": float("inf")}, {"not_before": float("nan")},
                     {"not_before": True}, {"not_before": 10**400}, {"excessive": "SYNTHETIC"},
                     {"legacy_date": (26, 13, 27, 12, 0, 7, 1)},
                     {"legacy_date": (26, 10, 27, 12, 0, 7, 99)}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                RetryAfter(**args)

    def test_http_error_transmits_only_retry_after_and_closes_unread_error_body(self):
        headers = Message()
        headers["Retry-After"] = "7"
        headers["Set-Cookie"] = "SYNTHETIC-CREDENTIAL"
        headers["Authorization"] = "SYNTHETIC-CREDENTIAL"
        class Body(BytesIO):
            def read(self, *args): raise AssertionError("Error body must not be read")
        body = Body(b"SYNTHETIC-CONTENT")
        error = HTTPError(URL + '?token=SYNTHETIC', 429, "SYNTHETIC", headers, body)
        with patch("metadata_http.build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaises(MetadataHTTPError) as caught:
                get_metadata_json(URL, policy=POLICY)
            build.return_value.open.assert_called_once()
        result = caught.exception
        self.assertTrue(body.closed)
        self.assertEqual(result.retry_after, RetryAfter(seconds=7))
        self.assertEqual(result.headers, {})
        self.assertEqual(result.url, "")
        self.assertEqual(result.read(), b"")
        self.assertNotIn("SYNTHETIC", str(result))
        self.assertTrue(result.__suppress_context__)

    def test_response_status_path_transmits_normalized_date_without_headers(self):
        class Response:
            status = 503
            headers = {"Retry-After": "Tue, 27 Oct 2026 12:00:07 GMT", "Set-Cookie": "SYNTHETIC"}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args): raise AssertionError("Error body must not be read")
        with patch("metadata_http.build_opener") as build:
            build.return_value.open.return_value = Response()
            with self.assertRaises(MetadataHTTPError) as caught:
                get_metadata_json(URL, policy=POLICY)
            build.return_value.open.assert_called_once()
        self.assertEqual(caught.exception.retry_after, parse_retry_after(Response.headers["Retry-After"]))
        self.assertEqual(caught.exception.headers, {})

    def test_invalid_retry_after_does_not_expose_headers_or_create_a_delay(self):
        error = HTTPError(URL, 503, "SYNTHETIC", {"Retry-After": "SYNTHETIC-CREDENTIAL", "Set-Cookie": "SYNTHETIC"}, None)
        with patch("metadata_http.build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaises(MetadataHTTPError) as caught:
                get_metadata_json(URL, policy=POLICY)
        self.assertIsNone(caught.exception.retry_after)
        self.assertEqual(caught.exception.headers, {})

    def test_injected_transport_uses_typed_retry_after_and_200_payload_is_unchanged(self):
        class Transport:
            def __init__(self, result): self.result = result; self.calls = 0
            def fetch(self, *args, **kwargs): self.calls += 1; return self.result
        for status in (200, 429):
            with self.subTest(status=status):
                transport = Transport(HTTPResult(status, b'{"id":"fixture"}', RetryAfter(seconds=3)))
                if status == 200:
                    self.assertEqual(get_metadata_json(URL, policy=POLICY, transport=transport), {"id": "fixture"})
                else:
                    with self.assertRaises(MetadataHTTPError) as caught:
                        get_metadata_json(URL, policy=POLICY, transport=transport)
                    self.assertEqual(caught.exception.retry_after, RetryAfter(seconds=3))
                self.assertEqual(transport.calls, 1)
        transport = Transport(HTTPResult(429, b"", "SYNTHETIC"))
        with self.assertRaises(MetadataResponseError):
            get_metadata_json(URL, policy=POLICY, transport=transport)


if __name__ == "__main__":
    unittest.main()
