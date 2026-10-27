"""B4.2 transport tests: simulated responses only, no external or local server."""

import socket
from http.client import HTTPResponse, IncompleteRead
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from metadata_http import (
    HTTPPolicy, HTTPResult, MetadataHTTPError, MetadataNetworkError,
    MetadataResponseError, MetadataTimeoutError, NoRedirect, UrllibTransport,
    get_metadata_json,
)
from metadata_primitives import error_summary
from metadata_sdk import MetadataSDKError, read_model_repository


URL = "https://metadata.example.test/v1/models?type=text2text"
POLICY = HTTPPolicy(frozenset({"metadata.example.test"}), 100, 20)


class FakeTransport:
    def __init__(self, result=HTTPResult(200, b'{"id":"fixture"}'), error=None):
        self.result, self.error, self.calls = result, error, []

    def fetch(self, request, *, timeout, max_bytes):
        self.calls.append((request, timeout, max_bytes))
        if self.error is not None:
            raise self.error
        return self.result


class MetadataHTTPTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo"):
            guard = patch(target, side_effect=AssertionError("Network forbidden in transport tests"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_200_json_validates_exact_get_and_limits_without_auth(self):
        transport = FakeTransport(HTTPResult(200, b'{"unknown":[null,false,0,[]]}'))
        self.assertEqual(get_metadata_json(URL, policy=POLICY, transport=transport), {"unknown": [None, False, 0, []]})
        self.assertEqual(len(transport.calls), 1)
        request, timeout, maximum = transport.calls[0]
        self.assertEqual(request.full_url, URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual((timeout, maximum), (20, 100))
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("Cookie", request.headers)

    def test_malformed_ambiguous_nonfinite_or_nonobject_json_rejected(self):
        for body in (b'<html>bad</html>', b'{"id":"a","id":"b"}', b'{"x":NaN}',
                     b'{"x":1e999}', b'[]', b'null', b'\xff', b''):
            with self.subTest(body=body):
                transport = FakeTransport(HTTPResult(200, body))
                with self.assertRaises(MetadataResponseError):
                    get_metadata_json(URL, policy=POLICY, transport=transport)
                self.assertEqual(len(transport.calls), 1)

    def test_secret_keys_in_response_rejected_without_sensitive_error_text(self):
        body = b'{"nested":[{"apiKey":"SYNTHETIC-DO-NOT-USE"}]}'
        with self.assertRaises(MetadataResponseError) as caught:
            get_metadata_json(URL, policy=POLICY, transport=FakeTransport(HTTPResult(200, body)))
        self.assertNotIn("SYNTHETIC", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_byte_limit_exact_boundary_and_one_extra_byte(self):
        body = b'{"id":"a"}'
        for limit, success in ((len(body), True), (len(body)-1, False)):
            policy = HTTPPolicy(POLICY.allowed_hosts, limit, 20)
            transport = FakeTransport(HTTPResult(200, body))
            if success:
                self.assertEqual(get_metadata_json(URL, policy=policy, transport=transport), {"id": "a"})
            else:
                with self.assertRaisesRegex(MetadataResponseError, "size limit"):
                    get_metadata_json(URL, policy=policy, transport=transport)

    def test_timeout_and_wrapped_timeout_have_no_automatic_retry(self):
        for error in (TimeoutError("SYNTHETIC"), socket.timeout("SYNTHETIC"), URLError(TimeoutError("SYNTHETIC"))):
            with self.subTest(error=type(error).__name__):
                transport = FakeTransport(error=error)
                with self.assertRaises(MetadataTimeoutError) as caught:
                    get_metadata_json(URL, policy=POLICY, transport=transport)
                self.assertNotIn("SYNTHETIC", str(caught.exception))
                self.assertEqual(len(transport.calls), 1)

    def test_network_error_is_sanitized(self):
        for error in (URLError("SYNTHETIC credential"), OSError("SYNTHETIC URL")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(MetadataNetworkError) as caught:
                    get_metadata_json(URL, policy=POLICY, transport=FakeTransport(error=error))
                self.assertNotIn("SYNTHETIC", str(caught.exception))

    def test_http_errors_keep_status_only_and_never_retry(self):
        for status in (301, 302, 307, 308, 401, 403, 404, 429, 500, 503):
            for mode in ("response", "exception"):
                with self.subTest(status=status, mode=mode):
                    transport = FakeTransport(HTTPResult(status, b'SYNTHETIC BODY'))
                    if mode == "exception":
                        transport.error = HTTPError(URL + '&token=SYNTHETIC', status, 'SYNTHETIC', {'Set-Cookie': 'SYNTHETIC'}, None)
                    with self.assertRaises(MetadataHTTPError) as caught:
                        get_metadata_json(URL, policy=POLICY, transport=transport)
                    error = caught.exception
                    self.assertIsInstance(error, HTTPError)
                    self.assertEqual(error.code, status)
                    self.assertEqual(error.url, "")
                    self.assertEqual(error.headers, {})
                    # HTTPError creates an empty BytesIO when fp=None. Keep its
                    # compatible file interface, but no upstream body bytes.
                    self.assertEqual(error.read(), b"")
                    self.assertNotIn("SYNTHETIC", str(error))
                    self.assertIn(f"HTTP {status}", error_summary("Fixture", error))
                    self.assertEqual(len(transport.calls), 1)

    def test_denied_origins_and_credential_urls_fail_before_transport(self):
        for url in ("http://metadata.example.test/v1/models", "https://evil.test/", "https://metadata.example.test.evil.test/",
                    "https://metadata.example.test:8443/", "https://user:pass@metadata.example.test/",
                    "https://metadata.example.test/#fragment", "https://metadata.example.test/?api_key=SYNTHETIC",
                    "https://metadata.example.test/?accessToken=SYNTHETIC", "https://metadata.example.test/\n",
                    "https://metadata.example.test./", "file:///tmp/metadata.json", "//metadata.example.test/"):
            with self.subTest(url=url):
                transport = FakeTransport()
                with self.assertRaises(ValueError):
                    get_metadata_json(url, policy=POLICY, transport=transport)
                self.assertEqual(transport.calls, [])

    def test_policy_rejects_implicit_hosts_invalid_limits_and_timeouts(self):
        for hosts, maximum, timeout in ((frozenset(), 100, 20), ('metadata.example.test', 100, 20),
                                         ({'*.example.test'}, 100, 20),
                                         ({'UPPER.test'}, 100, 20), (POLICY.allowed_hosts, 0, 20),
                                         (POLICY.allowed_hosts, True, 20), (POLICY.allowed_hosts, 100, 0),
                                         (POLICY.allowed_hosts, 100, float('inf')), (POLICY.allowed_hosts, 100, True),
                                         (POLICY.allowed_hosts, 100, 61)):
            with self.subTest(hosts=hosts, maximum=maximum, timeout=timeout), self.assertRaises(ValueError):
                HTTPPolicy(hosts, maximum, timeout)

    def test_urllib_reads_only_limit_plus_one_and_closes_response(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): self.closed = True
            def read(self, n): self.limit = n; return b'{"x":0}'
        response = Response()
        with patch("metadata_http.build_opener") as build:
            build.return_value.open.return_value = response
            self.assertEqual(get_metadata_json(URL, policy=POLICY), {"x": 0})
        self.assertEqual(response.limit, POLICY.max_response_bytes + 1)
        self.assertTrue(response.closed)
        self.assertIsInstance(build.call_args.args[0], NoRedirect)
        build.return_value.open.assert_called_once()
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://metadata.example.test/other"))

    def test_error_response_body_is_not_read(self):
        class Response:
            status = 503
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, n): raise AssertionError("Do not read an error body")
        with patch("metadata_http.build_opener") as build:
            build.return_value.open.return_value = Response()
            with self.assertRaises(MetadataHTTPError):
                get_metadata_json(URL, policy=POLICY)

    def test_interrupted_response_read_closes_stream_without_partial_json_or_retry(self):
        for error, expected in (
            (IncompleteRead(b'{"id":"SYNTHETIC-PARTIAL"}', 99), MetadataNetworkError),
            (ConnectionResetError("SYNTHETIC connection detail"), MetadataNetworkError),
            (TimeoutError("SYNTHETIC read timeout"), MetadataTimeoutError),
        ):
            with self.subTest(error=type(error).__name__):
                class Response:
                    status = 200
                    closed = False
                    reads = []
                    def __enter__(self): return self
                    def __exit__(self, *args): self.closed = True
                    def read(self, n):
                        self.reads.append(n)
                        raise error
                response = Response()
                with patch("metadata_http.build_opener") as build, \
                        patch("metadata_http.strict_json_loads") as decode:
                    build.return_value.open.return_value = response
                    with self.assertRaises(expected) as caught:
                        get_metadata_json(URL, policy=POLICY)
                    build.return_value.open.assert_called_once()
                    decode.assert_not_called()
                self.assertTrue(response.closed)
                self.assertEqual(response.reads, [POLICY.max_response_bytes + 1])
                self.assertNotIn("SYNTHETIC", str(caught.exception))
                self.assertNotIn("SYNTHETIC", error_summary("Fixture", caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)

    def test_short_content_length_body_is_rejected_even_if_bounded_read_returns_valid_json(self):
        # HTTPResponse.read(n) can return a short body without IncompleteRead.
        # Exercise the actual stdlib parser using in-memory wire bytes only.
        class Socket:
            def makefile(self, *args):
                return BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 50\r\n\r\n{"id":"SYNTHETIC-PARTIAL"}')
        response = HTTPResponse(Socket())
        response.begin()
        with patch("metadata_http.build_opener") as build, patch("metadata_http.strict_json_loads") as decode:
            build.return_value.open.return_value = response
            with self.assertRaises(MetadataNetworkError) as caught:
                get_metadata_json(URL, policy=POLICY)
            build.return_value.open.assert_called_once()
            decode.assert_not_called()
        self.assertTrue(response.closed)
        self.assertNotIn("SYNTHETIC", str(caught.exception))

    def test_content_length_bounds_and_valid_header_are_checked_before_json(self):
        for length, valid, reads in (("2", True, 1), (" 0002 ", True, 1),
                                     ("101", False, 0), ("9" * 5000, False, 0),
                                     ("invalid", False, 0), ("-1", False, 0),
                                     ("2, 3", False, 0), ("1", False, 1)):
            with self.subTest(length=length[:20]):
                class Response:
                    status = 200
                    headers = {"Content-Length": length}
                    reads = 0
                    closed = False
                    def __enter__(self): return self
                    def __exit__(self, *args): self.closed = True
                    def read(self, n): self.reads += 1; return b'{}'
                response = Response()
                with patch("metadata_http.build_opener") as build:
                    build.return_value.open.return_value = response
                    if valid:
                        self.assertEqual(get_metadata_json(URL, policy=POLICY), {})
                    else:
                        with self.assertRaises(MetadataResponseError):
                            get_metadata_json(URL, policy=POLICY)
                self.assertEqual(response.reads, reads)
                self.assertTrue(response.closed)

    def test_nim_404_remains_metadata_unavailable_only_for_selected_tag(self):
        from probe_source_adapters import NIM_RESOURCE, NIM_TAG, audit_nvidia_nim
        with patch("probe_source_adapters.get_json", side_effect=MetadataHTTPError(404)):
            result = audit_nvidia_nim(20, resource_id=NIM_RESOURCE, tag=NIM_TAG)
        self.assertEqual(result["metadata_status"], "unavailable_for_tag")
        for status in (401, 403, 429, 503):
            with self.subTest(status=status), patch("probe_source_adapters.get_json", side_effect=MetadataHTTPError(status)):
                with self.assertRaises(HTTPError):
                    audit_nvidia_nim(20, resource_id=NIM_RESOURCE, tag=NIM_TAG)

    def test_invalid_transport_result_rejected(self):
        for result in (None, HTTPResult(True, b'{}'), HTTPResult(999, b'{}'), HTTPResult(200, '{}')):
            with self.subTest(result=result), self.assertRaises(MetadataResponseError):
                get_metadata_json(URL, policy=POLICY, transport=FakeTransport(result))


class MetadataSDKTests(unittest.TestCase):
    def test_sdk_seam_calls_only_official_metadata_method_once(self):
        class Info:
            def to_dict(self): return {"repo_id": "example/model", "visibility": 5}
        class Client:
            def __init__(self): self.calls = []
            def get_repo(self, repo_id, *, repo_type):
                self.calls.append((repo_id, repo_type))
                return Info()
        client = Client()
        self.assertEqual(read_model_repository(client, "example/model"), {"repo_id": "example/model", "visibility": 5})
        self.assertEqual(client.calls, [("example/model", "model")])

    def test_sdk_errors_are_sanitized_without_optional_sdk_or_network(self):
        class Client:
            def get_repo(self, *args, **kwargs): raise RuntimeError("SYNTHETIC BODY")
        with self.assertRaises(MetadataSDKError) as caught:
            read_model_repository(Client(), "example/model")
        self.assertNotIn("SYNTHETIC", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_sdk_invalid_root_rejected(self):
        class Info:
            def to_dict(self): return []
        class Client:
            def get_repo(self, *args, **kwargs): return Info()
        with self.assertRaises(ValueError):
            read_model_repository(Client(), "example/model")


if __name__ == "__main__":
    unittest.main()
