from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = load_module("verify_phase9_metadata_local_m1", ROOT / "runner/verify_phase9_metadata_local_m1.py")
custody = load_module("phase9_metadata_custody", ROOT / "runner/phase9_metadata_custody.py")


class MetadataLocalM1Tests(unittest.TestCase):
    def test_static_contract_passes_without_provider_access(self):
        audit = gate.verify()
        self.assertEqual(
            audit["status"],
            "LOCAL_SYNTHETIC_PRECONDITIONS_PASS_REMOTE_EXECUTION_BLOCKED",
        )
        self.assertFalse(audit["bytecode_exact_match_checked"])
        for key in (
            "credentials_referenced",
            "external_jnlp_request_attempted",
            "jforex_connect_invoked",
            "availability_request_attempted",
            "provider_schedule_request_attempted",
            "market_price_request_attempted",
            "forbidden_market_period_request_attempted",
            "provider_schedule_inventory_acquired",
            "provider_schedule_allowlist_frozen",
            "acquisition_authorized",
            "count_only_authorized",
            "research_outcomes_calculated",
        ):
            self.assertFalse(audit[key], key)
        self.assertEqual(audit["phase9_price_files_acquired"], 0)
        self.assertEqual(audit["outcome_fields"], [])
        self.assertFalse(audit["compiled_against_real_jforex_api_2_13_99_jar"])
        self.assertFalse(audit["real_jforex_api_2_13_99_compatibility_verified"])
        self.assertFalse(audit["real_jforex_runtime_methodrefs_verified"])
        self.assertFalse(audit["java_path_toctou_resistant_connection_custody_verified"])
        self.assertEqual(len(audit["synthetic_api_fixture_sha256"]), 9)

    def test_source_byte_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            copied = Path(directory) / "jforex-metadata"
            shutil.copytree(ROOT / "runner/jforex-metadata", copied)
            target = copied / "src/main/java/org/phase9/metadata/Phase9MetadataClient.java"
            target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with mock.patch.object(gate, "MODULE", copied):
                with self.assertRaises(gate.GateError):
                    gate.validate_static_contract()

    def test_contract_state_and_remote_proposal_remain_unauthorized(self):
        local = json.loads((ROOT / "spec/metadata_only_local_m1_gate.frozen.json").read_text())
        remote = json.loads((ROOT / "spec/remote_jnlp_observation_amendment.frozen.json").read_text())
        self.assertTrue(local["authorization"]["local_synthetic_preflight_authorized"])
        self.assertFalse(local["authorization"]["external_jnlp_observation_authorized"])
        self.assertFalse(remote["authorization"]["user_approved_remote_jnlp_observation"])
        self.assertFalse(remote["workflow"]["implemented"])
        for value in remote["authorization"].values():
            self.assertFalse(value)
        self.assertEqual(
            remote["proposed_scope"]["initial_url"],
            "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp",
        )
        self.assertEqual(remote["proposed_scope"]["method"], "GET")
        self.assertEqual(remote["proposed_scope"]["credentials"], "NONE")
        self.assertFalse(remote["proposed_scope"]["jforex_connect"])
        self.assertFalse(remote["proposed_scope"]["execute_downloaded_code"])
        self.assertEqual(remote["proposed_scope"]["request_count_max"], 1)
        self.assertFalse(remote["proposed_scope"]["follow_redirects"])
        self.assertFalse(remote["proposed_scope"]["recursive_runtime_resource_requests"])

    def test_remote_proposal_byte_mutation_fails_closed(self):
        remote = json.loads((ROOT / "spec/remote_jnlp_observation_amendment.frozen.json").read_text())
        remote["proposed_scope"]["method"] = "HEAD"
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            changed = Path(directory) / "remote.json"
            changed.write_text(json.dumps(remote), encoding="utf-8")
            with mock.patch.object(gate, "REMOTE_PROPOSAL", changed):
                with self.assertRaises(gate.GateError):
                    gate.validate_static_contract()

    def test_dedicated_module_has_exact_sources_and_no_price_callbacks(self):
        sources = gate.module_sources()
        self.assertEqual(
            [path.name for path in sources],
            ["Phase9MetadataClient.java", "Phase9OfflineDomainPlugin.java"],
        )
        text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
        self.assertIn("getOfflineTimeDomains", text)
        self.assertIn("extends Plugin", text)
        self.assertIn("IClient", text)
        for prohibited in (
            "Phase9JForexAcquirer", "ITesterClient", "IStrategy", "onTick(", "onBar(",
            "getAvailableInstruments(", "setSubscribedInstruments(", "downloadData(",
        ):
            self.assertNotIn(prohibited, text)
        allowlist = json.loads(
            (ROOT / "spec/metadata_owned_method_allowlist.frozen.json").read_text()
        )["dukascopy_method_references"]
        self.assertEqual(allowlist, sorted(allowlist))

    def test_private_custody_rejects_root_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            anchor = Path(directory)
            os.chmod(anchor, 0o700)
            paths = custody.prepare(anchor, "123", "1")
            evidence = paths["evidence"] / "synthetic.txt"
            evidence.write_text("synthetic\n", encoding="ascii")
            os.chmod(evidence, 0o600)
            self.assertEqual(custody.validate_private_tree(paths["root"])["file_count"], 1)
            os.link(evidence, paths["evidence"] / "duplicate.txt")
            with self.assertRaises(custody.CustodyError):
                custody.validate_private_tree(paths["root"])
            link = anchor / "root-link"
            link.symlink_to(paths["root"], target_is_directory=True)
            with self.assertRaises(custody.CustodyError):
                custody.validate_private_tree(link)

    def test_private_custody_rejects_anchor_symlink(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            real = Path(directory) / "real"
            real.mkdir(mode=0o700)
            link = Path(directory) / "anchor-link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(custody.CustodyError):
                custody.prepare(link, "123", "1")

    def test_private_custody_scoped_cleanup(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            anchor = Path(directory)
            os.chmod(anchor, 0o700)
            paths = custody.prepare(anchor, "123", "1")
            result = custody.remove(paths["root"], anchor)
            self.assertFalse(result["post_delete_exists"])
            self.assertTrue(result["logical_removal_only_secure_erase_not_claimed"])
            with self.assertRaises(custody.CustodyError):
                custody.remove(anchor, anchor.parent)

    def test_private_custody_never_deletes_unprepared_prefix_tree(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            anchor = Path(directory)
            os.chmod(anchor, 0o700)
            foreign = anchor / "phase9-metadata-999-1"
            foreign.mkdir(mode=0o700)
            with self.assertRaises(custody.CustodyError):
                custody.remove(foreign, anchor)
            self.assertTrue(foreign.is_dir())

    def test_network_guard_compiles_and_contains_kernel_controls(self):
        source = ROOT / "runner/phase9_metadata_net_guard.c"
        value = source.read_text(encoding="utf-8")
        for required in (
            "LANDLOCK_ACCESS_NET_CONNECT_TCP", "LANDLOCK_RULE_NET_PORT",
            "PR_SET_SECCOMP", "__NR_fork", "__NR_clone3",
            "__NR_sendto", "AF_INET", "SOCK_TYPE_MASK", "SOCK_STREAM", "38443UL",
            "__NR_close_range", "S_ISSOCK",
            "0x40000000U",
            "__NR_setns", "__NR_unshare", "__NR_ptrace",
            "__NR_process_vm_writev", "__NR_pidfd_getfd",
            "LANDLOCK_ACCESS_FS_WRITE_FILE", "LANDLOCK_ACCESS_FS_MAKE_REG",
        ):
            self.assertIn(required, value)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            binary = Path(directory) / "guard"
            result = subprocess.run(
                ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_forbidden_class_match_uses_exact_class_boundary(self):
        forbidden = "com/dukascopy/api/IStrategy"
        boundary = re.escape(forbidden) + r"(?=$|[.;/$])"
        self.assertIsNone(re.search(
            boundary,
            "#8 = Utf8 com/dukascopy/api/IStrategyExceptionHandler\n",
            flags=re.MULTILINE,
        ))
        for observed in (
            "#7 = Class #8 // com/dukascopy/api/IStrategy\n",
            "Lcom/dukascopy/api/IStrategy;",
            "com/dukascopy/api/IStrategy$Nested",
        ):
            self.assertIsNotNone(re.search(boundary, observed, flags=re.MULTILINE))

    def test_workflow_is_targeted_local_synthetic_and_secret_free(self):
        workflow = (REPOSITORY_ROOT / ".github/workflows/phase9-metadata-local-m1-preflight.yml").read_text()
        self.assertIn("test_phase9_metadata_local_m1.py", workflow)
        self.assertIn("metadata-jforex-api", workflow)
        self.assertIn("--classes-dir", workflow)
        self.assertIn("run_phase9_metadata_network_synthetic.sh", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("ref: ${{ github.sha }}", workflow)
        for prohibited in (
            "secrets.", "curl ", "wget ", "mvn ", "jforex_3.jnlp",
            "Phase9JForexAcquirer", "DUKASCOPY_USERNAME", "DUKASCOPY_PASSWORD",
        ):
            self.assertNotIn(prohibited, workflow)


if __name__ == "__main__":
    unittest.main()
