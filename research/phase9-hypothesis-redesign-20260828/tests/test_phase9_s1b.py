from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = load_module("phase9_runtime_envelope", ROOT / "runner/preflight_runtime_envelope.py")
qc = load_module("phase9_full_qc", ROOT / "runner/phase9_full_qc.py")
POLICY = json.loads((ROOT / "data_manifest/runtime_envelope_policy.json").read_text())
UTC = timezone.utc


class RuntimeEnvelopeTests(unittest.TestCase):
    def test_run5_dependency_lock_is_exact(self):
        lock = POLICY["build_lock"]
        self.assertEqual(lock["maven_repository_inventory_line_count"], 930)
        self.assertEqual(
            lock["maven_repository_inventory_sha256"],
            "604f29b030b6f54f1e5d42d132b39784295dd1c6b633998a3a768e680fe557ab",
        )
        self.assertEqual(
            lock["runner_jar_sha256"],
            "545bb9601d547b0edd5476886474a9affb541df5dc1c3fe172cb544c7c1f8204",
        )
        self.assertEqual(lock["locked_jar_count"], 116)
        self.assertEqual(
            lock["locked_jar_manifest_sha256"],
            "8a6fca0cf65d80fc7ca0459ff56cf35ec6f92fe89b8f516de7bc8905ab941aeb",
        )

    def test_locked_jar_manifest_is_exact_and_unique(self):
        path = ROOT / "data_manifest/maven_jar_sha256.run33336895081.lock.txt"
        rows = runtime.parse_jar_lock(path, POLICY)
        self.assertEqual(len(rows), 116)
        self.assertEqual(len({relative for relative, _ in rows}), 116)
        self.assertTrue(all(len(digest) == 64 for _, digest in rows))

    def test_repository_urls_are_exact_https_bases_without_redirects(self):
        ordinary = runtime.repository_urls("org/example/demo/1/demo-1.jar", POLICY)
        dukascopy = runtime.repository_urls(
            "com/dukascopy/api/JForex-API/2.13.99/JForex-API-2.13.99.jar", POLICY
        )
        self.assertTrue(ordinary[0].startswith("https://repo.maven.apache.org/maven2/"))
        self.assertTrue(dukascopy[0].startswith("https://www.dukascopy.com/client/jforexlib/publicrepo/"))
        self.assertFalse(POLICY["locked_jar_download"]["redirects_allowed"])
        self.assertFalse(POLICY["locked_jar_download"]["environment_proxy_allowed"])

    def test_redirect_handler_fails_closed(self):
        handler = runtime.RejectRedirect()
        request = type("Request", (), {"full_url": "https://repo.maven.apache.org/a.jar"})()
        with self.assertRaises(Exception):
            handler.redirect_request(request, None, 302, "redirect", {}, "https://evil.example/a.jar")

    def test_hash_mismatch_never_promotes_download(self):
        payload = b"not-the-locked-jar"

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(payload))}

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                self.close()

            def geturl(self):
                return "https://repo.maven.apache.org/maven2/org/example/demo/1/demo-1.jar"

        class Opener:
            def open(self, request, timeout):
                return Response(payload)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                runtime.download_locked_jar(
                    "org/example/demo/1/demo-1.jar", hashlib.sha256(b"expected").hexdigest(),
                    root, POLICY, opener=Opener(),
                )
            self.assertFalse((root / "org/example/demo/1/demo-1.jar").exists())
            self.assertFalse((root / "org/example/demo/1/demo-1.jar.part").exists())

    def test_native_payloads_are_inventoried_by_suffix_and_magic(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "native.jar"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("linux/libgood.so", b"\x7fELFpayload")
                handle.writestr("windows/native.bin", b"MZpayload")
                handle.writestr("org/example/Ordinary.class", b"\xca\xfe\xba\xbebytecode")
                handle.writestr("ordinary.txt", b"plain")
            rows = runtime.scan_native_entries(archive, "fixture.jar")
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["magic"] for row in rows}, {"ELF", "PE"})

    def test_java_class_cafebabe_is_not_macho(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "classes.jar"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("Example.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
                handle.writestr("mac/libnative.dylib", b"\xca\xfe\xba\xbe\x00\x00\x00\x02")
            rows = runtime.scan_native_entries(archive, "fixture.jar")
            self.assertEqual([row["entry"] for row in rows], ["mac/libnative.dylib"])
            self.assertEqual(rows[0]["magic"], "MACHO")

    def test_archive_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            runtime.validate_archive_entry("../escape.so")
        with self.assertRaises(ValueError):
            runtime.validate_archive_entry("/absolute.so")

    def test_native_case_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "collision.jar"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("native/Lib.so", b"\x7fELFa")
                handle.writestr("native/lib.so", b"\x7fELFb")
            with self.assertRaises(ValueError):
                runtime.scan_native_entries(archive, "fixture.jar")

    def test_local_synthetic_jnlp_has_no_network_or_authorization_effect(self):
        fixture = (ROOT / "tests/fixtures/synthetic_safe_demo_shape.jnlp").read_bytes()
        audit = runtime.inspect_local_jnlp(
            fixture, POLICY["jnlp_static_policy"]["allowed_initial_url"], POLICY
        )
        self.assertFalse(audit["network_fetch_attempted"])
        self.assertFalse(audit["jforex_connect_invoked"])
        self.assertEqual([row["kind"] for row in audit["resources"]], ["jar", "nativelib", "extension"])

    def test_jnlp_dtd_entity_and_xinclude_are_rejected(self):
        url = POLICY["jnlp_static_policy"]["allowed_initial_url"]
        for payload in (
            b'<!DOCTYPE jnlp><jnlp/>',
            b'<!ENTITY bad "x"><jnlp/>',
            b'<jnlp><xi:include href="x"/></jnlp>',
            b'<jnlp xmlns:x="http://www.w3.org/2001/XInclude"><x:include href="x"/></jnlp>',
        ):
            with self.assertRaises(ValueError):
                runtime.inspect_local_jnlp(payload, url, POLICY)

    def test_jnlp_resource_path_traversal_is_rejected(self):
        url = POLICY["jnlp_static_policy"]["allowed_initial_url"]
        payload = b'<jnlp codebase="https://platform.dukascopy.com:443/demo_3/"><resources><jar href="../escape.jar"/></resources></jnlp>'
        with self.assertRaises(ValueError):
            runtime.inspect_local_jnlp(payload, url, POLICY)

    def test_jnlp_host_query_fragment_and_userinfo_are_rejected(self):
        host = "platform.dukascopy.com"
        for value in (
            "https://evil.example/demo.jnlp",
            "https://platform.dukascopy.com/demo.jnlp?token=x",
            "https://platform.dukascopy.com/demo.jnlp#x",
            "https://user@platform.dukascopy.com/demo.jnlp",
        ):
            with self.assertRaises(ValueError):
                runtime.strict_https_url(value, host)

    def test_gate_a_never_authorizes_acquisition(self):
        state = POLICY["authorization_after_gate_a"]
        self.assertTrue(all(value is False for value in state.values()))
        self.assertFalse(POLICY["gate_a"]["external_jnlp_request_allowed"])
        self.assertFalse(POLICY["gate_a"]["native_execution_allowed"])
        self.assertFalse(POLICY["gate_a"]["maven_execution_allowed"])
        self.assertFalse(POLICY["gate_a"]["java_execution_allowed"])
        self.assertTrue(POLICY["native_inventory"]["reject_java_class_cafebabe_as_macho"])


class FullQcPrimitiveTests(unittest.TestCase):
    def bar(self, timestamp: datetime, value: float = 1.0, volume: float = 10.0):
        return qc.Bar(timestamp, value, value + 0.1, value - 0.1, value + 0.05, volume)

    def test_missingness_includes_leading_interior_and_trailing_segments(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        expected = [start + timedelta(minutes=15 * index) for index in range(6)]
        result = qc.missing_segments(expected, expected[1:2] + expected[3:5], timedelta(minutes=15))
        self.assertEqual(result["scheduled_missing_slots"], 3)
        self.assertEqual(len(result["missing_segments"]), 3)
        self.assertFalse(result["segments_truncated"])

    def test_observed_closed_or_unknown_slot_is_rejected(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        with self.assertRaises(ValueError):
            qc.missing_segments([start], [start, start + timedelta(minutes=15)], timedelta(minutes=15))

    def test_observed_duplicate_schedule_slot_is_rejected(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        with self.assertRaises(ValueError):
            qc.missing_segments([start], [start, start], timedelta(minutes=15))

    def test_nonfinite_bar_is_rejected(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        with self.assertRaises(ValueError):
            qc.Bar(start, 1.0, float("nan"), 0.9, 1.0, 10)

    def test_m15_h1_exact_reconciliation_passes(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        bars = [self.bar(start + timedelta(minutes=15 * index), 1 + index / 10) for index in range(4)]
        h1 = qc.aggregate_bars(bars, start)
        result = qc.reconcile_m15_h1(bars, h1)
        self.assertEqual(result["status"], "ELIGIBLE_MATCH")
        self.assertEqual(result["present_m15_slots"], 4)

    def test_m15_h1_missing_source_does_not_fill(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        bars = [self.bar(start + timedelta(minutes=15 * index)) for index in range(3)]
        result = qc.reconcile_m15_h1(bars, self.bar(start))
        self.assertEqual(result["status"], "SOURCE_MISSING")

    def test_m15_outside_h1_bucket_is_rejected(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        bars = [self.bar(start + timedelta(minutes=15 * index)) for index in range(4)]
        bars.append(self.bar(start + timedelta(hours=1)))
        with self.assertRaises(ValueError):
            qc.reconcile_m15_h1(bars, self.bar(start))

    def test_m15_h1_value_mismatch_is_rejected(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        bars = [self.bar(start + timedelta(minutes=15 * index), 1 + index / 10) for index in range(4)]
        rebuilt = qc.aggregate_bars(bars, start)
        changed = qc.Bar(start, rebuilt.open, rebuilt.high + 0.01, rebuilt.low, rebuilt.close, rebuilt.volume)
        self.assertEqual(qc.reconcile_m15_h1(bars, changed)["status"], "VALUE_MISMATCH")

    def test_incomplete_h4_bucket_is_dropped(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        expected = [start + timedelta(hours=index) for index in range(4)]
        bars = [self.bar(value) for value in expected[:3]]
        result = qc.complete_bucket_audit(bars, expected, 4)
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["records"][0]["status"], "DROPPED_SOURCE_MISSING")

    def test_complete_h4_and_d1_buckets_are_deterministic(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        expected = [start + timedelta(hours=index) for index in range(24)]
        bars = [self.bar(value) for value in expected]
        first = qc.complete_bucket_audit(bars, expected, 4)
        second = qc.complete_bucket_audit(bars, expected, 4)
        daily = qc.complete_bucket_audit(bars, expected, 24)
        self.assertEqual(first["records"], second["records"])
        self.assertEqual(first["created_count"], 6)
        self.assertEqual(daily["created_count"], 1)

    def test_cross_market_subsetting_is_rejected(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        incomplete = {member: {start} for member in qc.FROZEN_GROUPS["FX8"][:-1]}
        with self.assertRaises(ValueError):
            qc.cross_market_overlap("FX8", incomplete)

    def test_cross_market_intersection_is_recorded_without_threshold(self):
        start = datetime(2014, 8, 28, tzinfo=UTC)
        members = qc.FROZEN_GROUPS["METALS2"]
        timestamps = {members[0]: {start}, members[1]: set()}
        result = qc.cross_market_overlap("METALS2", timestamps)
        self.assertEqual(result["intersection_count"], 0)
        self.assertEqual(result["missing_member_occurrences"], 1)

    def test_energy_missing_metadata_is_data_insufficient(self):
        result = qc.validate_energy_inventory({})
        self.assertEqual(result["status"], "DATA_INSUFFICIENT")
        self.assertFalse(result["count_only_allowed"])

    def test_synthetic_report_keeps_actual_gate_and_outcomes_blocked(self):
        result = qc.synthetic_report()
        self.assertTrue(result["synthetic_fixture_only"])
        self.assertFalse(result["actual_market_data_full_quality_gate_passed"])
        self.assertFalse(result["count_only_authorized"])
        self.assertFalse(result["research_outcomes_calculated"])
        self.assertEqual(result["outcome_fields"], [])
        self.assertEqual(result["forward_fill_count"], 0)


class WorkflowPolicyTests(unittest.TestCase):
    def test_s1b_workflow_is_manual_no_secret_no_price_only(self):
        workflow = (ROOT.parents[1] / ".github/workflows/phase9-s1b-runtime-qc-preflight.yml").read_text()
        self.assertIn("RUN_PHASE9_S1B_NO_SECRET_NO_PRICE_PREFLIGHT", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn('"github_checkout_ephemeral_token_used": True', workflow)
        self.assertIn('"dukascopy_or_market_credentials_referenced": False', workflow)
        for prohibited in (
            "secrets.", "secrets[", "github.token", "GITHUB_TOKEN", "environment:",
            "org.phase9.Phase9JForexAcquirer", "client.connect", "downloadData", "startStrategy",
            "DUKASCOPY_USERNAME", "DUKASCOPY_PASSWORD", "push:", "schedule:",
            "pull_request_target:", "actions/setup-java@", "mvn -", "java -jar",
        ):
            self.assertNotIn(prohibited, workflow)
        self.assertIn("--jar-lock", workflow)
        self.assertIn("--download-dir", workflow)
        self.assertIn('"maven_executed": False', workflow)
        self.assertIn('"java_executed": False', workflow)

    def test_locked_sources_are_verified_before_networked_byte_download(self):
        workflow = (ROOT.parents[1] / ".github/workflows/phase9-s1b-runtime-qc-preflight.yml").read_text()
        verify_position = workflow.index("Verify frozen anchors and S1B source identity")
        tests_position = workflow.index("python -m unittest discover")
        download_position = workflow.index("--download-dir")
        self.assertLess(verify_position, tests_position)
        self.assertLess(tests_position, download_position)
        self.assertIn("maven_jar_sha256.run33336895081.lock.txt", workflow)

    def test_s1b_artifact_is_exact_allowlist_staging(self):
        workflow = (ROOT.parents[1] / ".github/workflows/phase9-s1b-runtime-qc-preflight.yml").read_text()
        self.assertIn("artifact_manifest_sha256.txt", workflow)
        self.assertIn("allowed_filenames", workflow)
        self.assertIn("st_nlink != 1", workflow)
        self.assertIn("git status --porcelain=v1 --untracked-files=all", workflow)
        self.assertIn("S1B_UPLOAD_DIR", workflow)
        self.assertNotIn("${{ always() }}", workflow)


if __name__ == "__main__":
    unittest.main()
