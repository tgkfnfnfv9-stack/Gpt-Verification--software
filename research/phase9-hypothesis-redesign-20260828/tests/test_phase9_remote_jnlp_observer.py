import argparse
import copy
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest import mock
import sys


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


OBSERVER = load_module("phase9_remote_jnlp_observer", ROOT / "runner" / "phase9_remote_jnlp_observer.py")
VERIFIER = load_module("verify_phase9_remote_jnlp_observation", ROOT / "runner" / "verify_phase9_remote_jnlp_observation.py")
GATE = ROOT / "spec" / "remote_jnlp_initial_observation_gate.frozen.json"


class FakeRawSocket:
    def __init__(self):
        self.connects = []
        self.timeout = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def connect(self, sockaddr):
        self.connects.append(sockaddr)

    def close(self):
        self.closed = True


class FakeTLSSocket:
    def __init__(self, response):
        self.response = response
        self.sent = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def getpeername(self):
        return ("192.0.2.10", 443)

    def getpeercert(self, binary_form=False):
        self.binary_form = binary_form
        return b"synthetic-der-certificate"

    def version(self):
        return "TLSv1.3"

    def cipher(self):
        return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

    def sendall(self, value):
        self.sent.append(value)

    def makefile(self, *_args, **_kwargs):
        return BytesIO(self.response)


class FakeSSLContext:
    def __init__(self, tls_socket):
        self.tls_socket = tls_socket
        self.check_hostname = None
        self.verify_mode = None
        self.keylog_filename = "would-have-leaked"
        self.server_hostname = None

    def wrap_socket(self, raw_socket, server_hostname):
        self.raw_socket = raw_socket
        self.server_hostname = server_hostname
        return self.tls_socket


def args(**overrides):
    values = {
        "confirmation": OBSERVER.EXACT_CONFIRMATION,
        "github_event_name": "workflow_dispatch",
        "github_ref": "refs/heads/main",
        "github_sha": "a" * 40,
        "github_run_id": "123",
        "github_run_number": "1",
        "github_run_attempt": "1",
        "github_job": "observe",
        "timeout_seconds": 5.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def run_fake(response: bytes):
    raw = FakeRawSocket()
    tls = FakeTLSSocket(response)
    context = FakeSSLContext(tls)
    dns = [
        (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2001:db8::10", 443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.10", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.20", 443)),
    ]
    with mock.patch.object(OBSERVER.socket, "getaddrinfo", return_value=dns) as resolver, \
            mock.patch.object(OBSERVER.socket, "socket", return_value=raw) as socket_factory, \
            mock.patch.object(OBSERVER.ssl, "create_default_context", return_value=context):
        audit = OBSERVER.observe(args(), VERIFIER.EXPECTED_GATE_SHA256)
    return audit, raw, tls, context, resolver, socket_factory


class GateTests(unittest.TestCase):
    def test_frozen_gate_validates(self):
        gate, digest = OBSERVER.validate_gate(GATE)
        self.assertTrue(gate["single_use_authorization"]["user_approved"])
        self.assertEqual(len(digest), 64)

    def test_gate_url_variant_rejected_before_network(self):
        value = json.loads(GATE.read_text(encoding="utf-8"))
        mutations = [
            "https://platform.dukascopy.com/demo_3/jforex_3.jnlp",
            "http://platform.dukascopy.com:443/demo_3/jforex_3.jnlp",
            "https://platform.dukascopy.com:443/demo_3/../demo_3/jforex_3.jnlp",
            "https://user@platform.dukascopy.com:443/demo_3/jforex_3.jnlp",
            "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp?q=1",
            "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp#x",
        ]
        for url in mutations:
            with self.subTest(url=url), tempfile.TemporaryDirectory() as temp:
                changed = json.loads(json.dumps(value))
                changed["exact_scope"]["initial_url"] = url
                changed["exact_scope"]["allowed_urls_exact_set"] = [url]
                path = Path(temp) / "gate.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(OBSERVER.ObservationError):
                    OBSERVER.validate_gate(path)

    def test_static_workflow_and_gate_verifier_passes(self):
        result = VERIFIER.verify_static()
        self.assertTrue(result["workflow_dispatch_only"])
        self.assertFalse(result["acquisition_authorized"])


class ParserTests(unittest.TestCase):
    def test_references_are_observed_not_fetched(self):
        body = b'''<?xml version="1.0"?>
<jnlp codebase="https://cdn.example/base/" href="launch.jnlp">
  <resources><jar href="app.jar"/><extension href="https://other.example/e.jnlp"/></resources>
</jnlp>'''
        with mock.patch.object(OBSERVER.socket, "getaddrinfo", side_effect=AssertionError("network used")):
            parsed = OBSERVER.parse_jnlp_identity(body, "identity")
        self.assertEqual(parsed["reference_count"], 3)
        self.assertEqual(parsed["references"][1]["resolved_url"], "https://cdn.example/base/app.jar")
        self.assertEqual(parsed["references"][2]["authorization_status"], "OBSERVED_ONLY_NOT_ALLOWED")
        self.assertTrue(all(row["fetched"] is False for row in parsed["references"]))

    def test_active_xml_features_and_xinclude_are_rejected(self):
        bodies = [
            b'<!DOCTYPE jnlp [<!ENTITY x "boom">]><jnlp>&x;</jnlp>',
            b'<?phase9 active?><jnlp/>',
            b'<jnlp xmlns:z="http://www.w3.org/2001/XInclude"><z:include href="x"/></jnlp>',
        ]
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(OBSERVER.ObservationError):
                OBSERVER.parse_jnlp_identity(body, "identity")

    def test_non_identity_encoding_is_not_parsed(self):
        result = OBSERVER.parse_jnlp_identity(b"not xml", "gzip")
        self.assertEqual(result["status"], "SKIPPED_NON_IDENTITY_CONTENT_ENCODING")


class TransportTests(unittest.TestCase):
    def test_single_exact_get_and_tls_identity(self):
        body = b'<jnlp codebase="https://cdn.example/"><resources><jar href="a.jar"/></resources></jnlp>'
        response = b"HTTP/1.1 200 OK\r\nContent-Type: application/x-java-jnlp-file\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        audit, raw, tls, context, resolver, socket_factory = run_fake(response)
        self.assertEqual(audit["status"], "INITIAL_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED")
        self.assertEqual(audit["transport"]["dns_resolution_call_count"], 1)
        self.assertEqual(audit["transport"]["tcp_connect_attempt_count"], 1)
        self.assertEqual(audit["transport"]["http_request_count"], 1)
        resolver.assert_called_once_with(OBSERVER.EXACT_HOST, 443, type=socket.SOCK_STREAM)
        socket_factory.assert_called_once()
        self.assertEqual(raw.connects, [("192.0.2.10", 443)])
        self.assertEqual(context.server_hostname, OBSERVER.EXACT_HOST)
        self.assertIsNone(context.keylog_filename)
        self.assertEqual(len(tls.sent), 1)
        sent = tls.sent[0]
        self.assertTrue(sent.startswith(b"GET /demo_3/jforex_3.jnlp HTTP/1.1\r\n"))
        self.assertIn(b"Host: platform.dukascopy.com:443\r\n", sent)
        self.assertIn(b"Accept-Encoding: identity\r\n", sent)
        for forbidden in (b"Authorization:", b"Cookie:", b"Proxy-Authorization:"):
            self.assertNotIn(forbidden, sent)
        self.assertEqual(audit["response"]["body_sha256_if_status_200"], OBSERVER.sha256_bytes(body))
        self.assertNotIn(body.decode(), json.dumps(audit))
        self.assertEqual(VERIFIER.verify_audit_dict(audit), audit)

    def test_redirect_records_location_without_follow_or_body_read(self):
        sentinel = b"RAW-REDIRECT-BODY-MUST-NOT-APPEAR"
        response = b"HTTP/1.1 302 Found\r\nLocation: https://redirect.invalid/next\r\nContent-Length: " + str(len(sentinel)).encode() + b"\r\n\r\n" + sentinel
        audit, raw, tls, _context, resolver, socket_factory = run_fake(response)
        self.assertEqual(audit["status"], "REDIRECT_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED")
        self.assertEqual(audit["response"]["redirect_location"], "https://redirect.invalid/next")
        self.assertEqual(audit["transport"]["http_request_count"], 1)
        self.assertEqual(audit["request_scope"]["redirect_followed"], False)
        self.assertEqual(audit["request_scope"]["recursive_resource_fetch_count"], 0)
        self.assertNotIn(sentinel.decode(), json.dumps(audit))
        resolver.assert_called_once()
        socket_factory.assert_called_once()

    def test_oversize_and_ambiguous_framing_are_terminal(self):
        fixtures = [
            b"HTTP/1.1 200 OK\r\nContent-Length: 2097153\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\nx",
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Length: 1\r\n\r\n1\r\nx\r\n0\r\n\r\n",
        ]
        for response in fixtures:
            with self.subTest(response=response[:80]):
                audit, *_ = run_fake(response)
                self.assertEqual(audit["status"], "ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED")
                self.assertEqual(audit["transport"]["http_request_count"], 1)
                self.assertIsNotNone(audit["error_type"])
                self.assertEqual(VERIFIER.verify_audit_dict(audit), audit)

    def test_invalid_run_identity_never_resolves(self):
        with mock.patch.object(OBSERVER.socket, "getaddrinfo", side_effect=AssertionError("network used")) as resolver:
            audit = OBSERVER.observe(args(github_run_number="2"), "f" * 64)
        resolver.assert_not_called()
        self.assertEqual(audit["transport"]["http_request_count"], 0)
        self.assertEqual(audit["status"], "ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED")

    def test_audit_verifier_rejects_raw_fields_and_invariant_mutations(self):
        body = b'<jnlp><resources><jar href="https://cdn.example/a.jar"/></resources></jnlp>'
        response = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        valid, *_ = run_fake(response)
        VERIFIER.verify_audit_dict(valid)
        mutations = []

        raw = copy.deepcopy(valid)
        raw["raw_jnlp_bytes"] = body.decode()
        mutations.append(raw)

        credentials = copy.deepcopy(valid)
        credentials["request_scope"]["credentials"] = "LEAKED"
        mutations.append(credentials)

        proxy = copy.deepcopy(valid)
        proxy["request_scope"]["proxy_used"] = True
        mutations.append(proxy)

        execution = copy.deepcopy(valid)
        execution["request_scope"]["downloaded_code_executed"] = True
        mutations.append(execution)

        count = copy.deepcopy(valid)
        count["transport"]["http_request_count"] = 0
        mutations.append(count)

        tls = copy.deepcopy(valid)
        tls["transport"]["tls_peer_certificate_sha256"] = None
        mutations.append(tls)

        oversize = copy.deepcopy(valid)
        oversize["response"]["body_bytes_if_status_200"] = 2_097_153
        mutations.append(oversize)

        fetched = copy.deepcopy(valid)
        fetched["jnlp_identity"]["references"][0]["fetched"] = True
        mutations.append(fetched)

        extra_nested = copy.deepcopy(valid)
        extra_nested["response"]["raw_body"] = body.decode()
        mutations.append(extra_nested)

        address = copy.deepcopy(valid)
        address["transport"]["selected_address"]["raw_body"] = body.decode()
        mutations.append(address)

        outcome_in_list = copy.deepcopy(valid)
        outcome_in_list["jnlp_identity"]["references"][0]["return_sign"] = "hidden"
        mutations.append(outcome_in_list)

        cipher = copy.deepcopy(valid)
        cipher["transport"]["tls_cipher"][1] = {"raw_body": body.decode()}
        mutations.append(cipher)

        run_id = copy.deepcopy(valid)
        run_id["github_identity"]["run_id"] = "not-a-run"
        mutations.append(run_id)

        for index, mutated in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(VERIFIER.VerificationError):
                VERIFIER.verify_audit_dict(mutated)

    def test_exact_two_file_artifact_verifies(self):
        body = b'<jnlp/>'
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\n\r\n" + body
        audit, *_ = run_fake(response)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            audit_path = directory / "REMOTE_JNLP_INITIAL_OBSERVATION_AUDIT.json"
            audit_path.write_text(json.dumps(audit, sort_keys=True) + "\n", encoding="utf-8")
            manifest = directory / "artifact_manifest_sha256.txt"
            manifest.write_text(
                f"{VERIFIER.sha256_file(audit_path)}  {audit_path.name}\n", encoding="utf-8"
            )
            self.assertEqual(VERIFIER.verify_artifact(directory), audit)

    def test_output_is_new_private_file_and_contains_no_raw_body(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private" / "audit.json"
            value = {"body_sha256": OBSERVER.sha256_bytes(b"secret-body")}
            OBSERVER.write_new_json(path, value)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotIn("secret-body", path.read_text(encoding="utf-8"))
            with self.assertRaises(OBSERVER.ObservationError):
                OBSERVER.write_new_json(path, value)


if __name__ == "__main__":
    unittest.main()
