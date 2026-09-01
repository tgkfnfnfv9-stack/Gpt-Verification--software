from __future__ import annotations

import argparse
import copy
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import socket
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


OBSERVER = load_module(
    "phase9_remote_libs_jnlp_observer",
    ROOT / "runner/phase9_remote_libs_jnlp_observer.py",
)
VERIFIER = load_module(
    "verify_phase9_remote_libs_jnlp_observation",
    ROOT / "runner/verify_phase9_remote_libs_jnlp_observation.py",
)
GATE = ROOT / "spec/remote_libs_jnlp_observation_gate.frozen.json"


class FakeRawSocket:
    def __init__(self):
        self.connects = []

    def settimeout(self, value):
        self.timeout = value

    def connect(self, sockaddr):
        self.connects.append(sockaddr)

    def close(self):
        pass


class FakeTLSSocket:
    def __init__(self, response):
        self.response = response
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def getpeername(self):
        return ("192.0.2.10", 443)

    def getpeercert(self, binary_form=False):
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
        self.keylog_filename = "leak"

    def wrap_socket(self, raw_socket, server_hostname):
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


def run_fake(body: bytes):
    response = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/x-java-jnlp-file\r\n"
        + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    )
    raw = FakeRawSocket()
    tls = FakeTLSSocket(response)
    context = FakeSSLContext(tls)
    dns = [(
        socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
        ("192.0.2.10", 443),
    )]
    utility = OBSERVER.utility
    with mock.patch.object(utility.socket, "getaddrinfo", return_value=dns), \
            mock.patch.object(utility.socket, "socket", return_value=raw), \
            mock.patch.object(utility.ssl, "create_default_context", return_value=context):
        audit = OBSERVER.observe(args(), VERIFIER.EXPECTED_GATE_SHA256)
    return audit, raw, tls, context


class GateTests(unittest.TestCase):
    def test_frozen_gate_and_source_evidence_validate(self):
        gate, digest = OBSERVER.validate_gate(GATE)
        self.assertEqual(digest, VERIFIER.EXPECTED_GATE_SHA256)
        self.assertEqual(gate["exact_scope"]["allowed_urls_exact_set"], [OBSERVER.EXACT_URL])
        self.assertFalse(gate["single_use_authorization"]["retry_authorized"])

    def test_exact_url_is_prior_observed_and_never_requested(self):
        gate = json.loads(GATE.read_text(encoding="utf-8"))
        self.assertEqual(gate["source_evidence"]["source_request_count_for_exact_url"], 0)
        self.assertEqual(
            gate["source_evidence"]["source_entry_kind"],
            "OBSERVED_EXTENSION_HREF_NOT_REQUESTED",
        )

    def test_static_workflow_verification_passes(self):
        value = VERIFIER.verify_static()
        self.assertFalse(value["acquisition_authorized"])
        self.assertFalse(value["research_outcomes_calculated"])


class ObservationTests(unittest.TestCase):
    def test_one_exact_get_parses_references_without_fetching(self):
        body = (
            b'<jnlp codebase="https://cdn.example/runtime/">'
            b'<resources><jar href="a.jar"/><jar href="b.jar"/></resources></jnlp>'
        )
        audit, raw, tls, context = run_fake(body)
        self.assertEqual(
            audit["status"],
            "LIBS_IDENTITY_OBSERVED_RESOURCE_REQUESTS_BLOCKED",
        )
        self.assertEqual(audit["transport"]["http_request_count"], 1)
        self.assertEqual(len(raw.connects), 1)
        self.assertEqual(context.server_hostname, OBSERVER.EXACT_HOST)
        self.assertIsNone(context.keylog_filename)
        self.assertTrue(tls.sent[0].startswith(b"GET /demo_3/libs_3.jnlp HTTP/1.1\r\n"))
        self.assertEqual(audit["jnlp_identity"]["reference_count"], 2)
        self.assertTrue(all(not row["fetched"] for row in audit["jnlp_identity"]["references"]))
        VERIFIER.verify_audit_dict(audit)

    def test_invalid_run_identity_never_uses_network(self):
        utility = OBSERVER.utility
        with mock.patch.object(
            utility.socket, "getaddrinfo", side_effect=AssertionError("network used")
        ) as resolver:
            audit = OBSERVER.observe(args(github_run_number="2"), VERIFIER.EXPECTED_GATE_SHA256)
        resolver.assert_not_called()
        self.assertEqual(audit["transport"]["http_request_count"], 0)
        self.assertEqual(audit["status"], "ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED")

    def test_verifier_rejects_outcome_and_fetched_reference(self):
        audit, *_ = run_fake(b'<jnlp><resources><jar href="a.jar"/></resources></jnlp>')
        outcome = copy.deepcopy(audit)
        outcome["prohibited_activity"]["outcome_fields"] = ["return"]
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify_audit_dict(outcome)
        fetched = copy.deepcopy(audit)
        fetched["jnlp_identity"]["references"][0]["fetched"] = True
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify_audit_dict(fetched)

    def test_exact_two_file_artifact(self):
        audit, *_ = run_fake(b"<jnlp/>")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            audit_path = directory / VERIFIER.AUDIT_FILE
            audit_path.write_text(json.dumps(audit, sort_keys=True) + "\n", encoding="utf-8")
            (directory / "artifact_manifest_sha256.txt").write_text(
                f"{VERIFIER.sha256_file(audit_path)}  {VERIFIER.AUDIT_FILE}\n",
                encoding="utf-8",
            )
            VERIFIER.verify_artifact(directory)


if __name__ == "__main__":
    unittest.main()
