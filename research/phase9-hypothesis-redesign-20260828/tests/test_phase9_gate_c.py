from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate_c = load_module("phase9_gate_c", ROOT / "runner/phase9_gate_c_inventory.py")
prefetch = load_module("phase9_gate_c_prefetch", ROOT / "runner/prefetch_phase9_maven_closure.py")


class GateCInventoryTests(unittest.TestCase):
    EXEC_CHAIN = (
        'execve("{SETPRIV}", ["setpriv", "--reuid=1000", "--regid=1000", "--clear-groups", "--no-new-privs"], 0) = 0\n'
        'execve("{ENV}", ["env", "-i"], 0) = 0\n'
        'execve("{JAVA}", ["java", "-XX:-UsePerfData", "org.phase9.gatec.GateCNativeMapProbe"], 0) = 0\n'
    )
    def test_run5_maven_build_closure_is_exact_and_prefetched_before_maven(self):
        lock = ROOT / "data_manifest/maven_build_artifact_sha256.run33336895081.lock.txt"
        rows = prefetch.parse_lock(lock)
        self.assertEqual(len(rows), 341)
        self.assertEqual(sum(path.endswith(".jar") for path, _ in rows), 116)
        self.assertEqual(sum(path.endswith(".pom") for path, _ in rows), 225)
        source = (ROOT / "runner/prefetch_phase9_maven_closure.py").read_text(encoding="utf-8")
        for prohibited in ("subprocess", "TesterFactory", "jforex_3.jnlp", "client.connect", "downloadData"):
            self.assertNotIn(prohibited, source)

    def test_prefetch_uses_only_the_repository_copy_matching_the_frozen_sha(self):
        class Response:
            def __init__(self, url, body):
                self.url = url
                self.body = io.BytesIO(body)
                self.headers = {"Content-Length": str(len(body))}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def geturl(self):
                return self.url

            def read(self, size):
                return self.body.read(size)

        class Opener:
            def __init__(self, bodies):
                self.bodies = iter(bodies)

            def open(self, request, timeout):
                return Response(request.full_url, next(self.bodies))

        expected_bytes = b"frozen historical pom\n"
        expected_sha = prefetch.hashlib.sha256(expected_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            prefetch,
            "REPOSITORY_BASES",
            ("https://first.example/", "https://second.example/"),
        ):
            root = Path(directory) / "repository"
            record = prefetch.download(
                "example/artifact/1/artifact-1.pom",
                expected_sha,
                root,
                Opener((b"different repository copy\n", expected_bytes)),
            )
            self.assertEqual(record["source_url"], "https://second.example/example/artifact/1/artifact-1.pom")
            self.assertEqual(
                (root / "example/artifact/1/artifact-1.pom").read_bytes(),
                expected_bytes,
            )

    def test_prefetch_rejects_when_no_repository_copy_matches_the_frozen_sha(self):
        class Response:
            headers = {"Content-Length": "5"}

            def __init__(self, url, body):
                self.url = url
                self.body = io.BytesIO(body)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def geturl(self):
                return self.url

            def read(self, size):
                return self.body.read(size)

        class Opener:
            def __init__(self):
                self.bodies = iter((b"wrong", b"other"))

            def open(self, request, timeout):
                return Response(request.full_url, next(self.bodies))

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            prefetch,
            "REPOSITORY_BASES",
            ("https://first.example/", "https://second.example/"),
        ):
            root = Path(directory) / "repository"
            with self.assertRaisesRegex(prefetch.PrefetchError, "every available repository"):
                prefetch.download(
                    "example/artifact/1/artifact-1.pom",
                    "0" * 64,
                    root,
                    Opener(),
                )
            self.assertFalse((root / "example/artifact/1/artifact-1.pom").exists())

    def test_c1_workflow_is_manual_metadata_only_and_never_invokes_acquirer(self):
        workflow = (ROOT.parents[1] / ".github/workflows/phase9-gate-c1-runtime-inventory.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("  push:\n    branches:\n      - main", workflow)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("RUN_PHASE9_GATE_C1_NO_SECRET_NO_PRICE", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("sudo unshare --net", workflow)
        self.assertIn("--propagation private", workflow)
        self.assertIn("prefetch_phase9_maven_closure.py", workflow)
        self.assertNotIn("mvn -B -ntp -Dmaven.repo.local", workflow)
        self.assertEqual(workflow.count("mvn -B -ntp -o"), 1)
        self.assertNotIn("if: ${{ always() }}", workflow)
        self.assertIn("bounded no-secret probe diagnostics", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("org.phase9.Phase9JForexAcquirer", workflow)
        self.assertNotIn("TesterFactory", workflow)
        self.assertNotIn("jforex_3.jnlp", workflow)
        self.assertNotIn("client.connect", workflow)
        self.assertNotIn("getAvailableInstruments", workflow)
        self.assertNotIn("downloadData", workflow)
        self.assertNotIn("startStrategy", workflow)
        self.assertIn("-iname '*.csv'", workflow)
        sandbox = (ROOT / "runner/run_gate_c_probe_sandbox.sh").read_text(encoding="utf-8")
        self.assertIn("--reuid=", sandbox)
        self.assertIn("--regid=", sandbox)
        self.assertIn("--clear-groups", sandbox)
        self.assertIn("--no-new-privs", sandbox)
        self.assertIn("remount,bind,ro /", sandbox)
        self.assertNotIn("mount --bind / /", sandbox)
        self.assertIn("findmnt -rn -o TARGET", sandbox)
        self.assertIn("mount_inventory", sandbox)
        self.assertIn("raw_mountinfo.txt", sandbox)
        self.assertIn("effective_mount_inventory.txt", sandbox)
        self.assertIn("derive_effective_mount_inventory.awk", sandbox)
        self.assertIn("gate_c_unexpected_rw_mount_target=%q", sandbox)
        self.assertIn("gate_c_unexpected_rw_mount_options=%q", sandbox)
        self.assertIn("gate_c_raw_mount=id:", sandbox)
        self.assertIn("/proc/self/mountinfo", sandbox)
        self.assertIn('findmnt -T "$target"', sandbox)
        self.assertIn("gate_c_effective_mount=", sandbox)
        self.assertIn("strace -s 0 -v -ff", sandbox)
        self.assertIn("-e trace=process,network", sandbox)
        self.assertIn('evidence_root="$gate_root/evidence-private"', sandbox)
        self.assertIn('work_root="$gate_root/probe-work"', sandbox)
        self.assertIn('strace -s 0 -v -ff -o "$evidence_root/trace"', sandbox)
        self.assertIn("gate_c_sandbox_failure_line=", sandbox)
        self.assertIn('chown -R "$target_uid:$target_gid" "$evidence_root"', sandbox)
        self.assertLess(sandbox.index("strace -s 0 -v -ff"), sandbox.index("--reuid="))
        self.assertIn("mount_inventory.txt", workflow)
        self.assertIn("effective_mount_inventory.txt", workflow)
        self.assertIn("raw_mountinfo.txt", workflow)
        self.assertIn("syscall_trace.txt", workflow)
        self.assertNotIn('zstd="$GATE_C_ROOT/native/', workflow)

    def test_effective_mount_inventory_keeps_only_leaf_mounts(self):
        mountinfo = """\
100 1 0:1 / / rw,relatime - ext4 /dev/root rw
101 100 0:1 / / ro,relatime - ext4 /dev/root rw
102 101 0:2 / /probe-work rw,relatime - tmpfs tmpfs rw
103 101 0:3 / /proc ro,nosuid,nodev,noexec - proc proc rw
104 103 0:4 / /proc/sys/fs/binfmt_misc rw,relatime - autofs systemd-1 rw
105 104 0:5 / /proc/sys/fs/binfmt_misc ro,nosuid,nodev,noexec - binfmt_misc binfmt_misc rw
"""
        result = subprocess.run(
            ["awk", "-f", str(ROOT / "runner/derive_effective_mount_inventory.awk")],
            input=mountinfo,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "/ ro,relatime",
                "/probe-work rw,relatime",
                "/proc ro,nosuid,nodev,noexec",
                "/proc/sys/fs/binfmt_misc ro,nosuid,nodev,noexec",
            ],
        )

    def test_effective_mount_inventory_rejects_malformed_input(self):
        result = subprocess.run(
            ["awk", "-f", str(ROOT / "runner/derive_effective_mount_inventory.awk")],
            input="not mountinfo\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_c1_scanner_has_no_network_subprocess_or_market_runtime(self):
        source = (ROOT / "runner/phase9_gate_c_inventory.py").read_text(encoding="utf-8")
        for prohibited in (
            "urllib",
            "requests",
            "subprocess",
            "socket.",
            "TesterFactory",
            "client.connect",
            "downloadData",
            "startStrategy",
            "DUKASCOPY_USERNAME",
            "DUKASCOPY_PASSWORD",
        ):
            self.assertNotIn(prohibited, source)

    def fixture(self, manifest_extra: str = "", extra_native: bool = False, omit_native: str | None = None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        entries = {}
        host = {
            "linux/amd64/libzstd-jni-1.5.7-6.so": b"\x7fELFzstd",
            "com/sun/jna/linux-amd64/libjnidispatch.so": b"\x7fELFjna",
        }
        for index in range(26):
            host[f"other/os/native-{index}.so"] = b"\x7fELF" + bytes([index])
        archives = [{"entries": []}]
        for name, data in host.items():
            entries[name] = data
            archives[0]["entries"].append({
                "entry": name,
                "entry_size": len(data),
                "entry_sha256": gate_c.sha256_bytes(data),
                "magic": "ELF",
                "suffix_match": True,
            })
        allowlist = root / "allowlist.json"
        allowlist.write_text(json.dumps({"archives": archives}), encoding="utf-8")
        runner = root / "runner.jar"
        manifest = (
            "Manifest-Version: 1.0\n"
            "Main-Class: org.phase9.Phase9JForexAcquirer\n"
            "Premain-Class: org.phase9.RuntimeClassOriginGuard\n"
            "Can-Redefine-Classes: false\n"
            "Can-Retransform-Classes: false\n"
            f"{manifest_extra}\n"
        ).encode()
        with zipfile.ZipFile(runner, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", manifest)
            archive.writestr("org/phase9/Safe.class", b"\xca\xfe\xba\xbe")
            for name, data in entries.items():
                if name != omit_native:
                    archive.writestr(name, data)
            if extra_native:
                archive.writestr("unknown/additional.so", b"\x7fELFx")
        return root, allowlist, runner

    def scan(self, root: Path, allowlist: Path, runner: Path):
        with mock.patch.object(gate_c, "EXPECTED_RUNNER_SHA256", gate_c.sha256_file(runner)), mock.patch.object(
            gate_c, "EXPECTED_ALLOWLIST_SHA256", gate_c.sha256_file(allowlist)
        ):
            return gate_c.scan_runner(runner, allowlist, root / "native")

    def test_exact_shaded_native_set_is_inventory_only(self):
        root, allowlist, runner = self.fixture()
        result = self.scan(root, allowlist, runner)
        self.assertEqual(result["native_entry_count"], 28)
        self.assertEqual(len(result["host_native_extractions"]), 1)
        self.assertEqual(result["gate_b_source_native_entries_not_shaded"], [])
        self.assertFalse(result["runtime_code_closure_verified"])
        self.assertFalse(result["acquisition_authorized"])
        self.assertFalse(result["count_only_authorized"])
        self.assertFalse(result["outcomes_authorized"])
        self.assertEqual(result["phase9_price_files_acquired"], 0)
        self.assertEqual(result["outcome_fields"], [])

    def test_gate_b_source_native_absent_from_shaded_runner_is_recorded_not_authorized(self):
        omitted = "linux/amd64/libzstd-jni-1.5.7-6.so"
        root, allowlist, runner = self.fixture(omit_native=omitted)
        result = self.scan(root, allowlist, runner)
        self.assertEqual(result["native_entry_count"], 27)
        self.assertEqual(result["gate_b_source_native_entries_not_shaded"], [omitted])
        self.assertFalse(result["same_run_inventory_may_authorize"])
        self.assertFalse(result["acquisition_authorized"])

    def test_additional_native_is_rejected(self):
        root, allowlist, runner = self.fixture(extra_native=True)
        with self.assertRaises(gate_c.GateCError):
            self.scan(root, allowlist, runner)

    def test_external_manifest_class_path_is_rejected(self):
        root, allowlist, runner = self.fixture("Class-Path: remote.jar")
        with self.assertRaises(gate_c.GateCError):
            self.scan(root, allowlist, runner)

    def runtime_fixture(self, trace: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        native = root / "native"
        native.mkdir()
        records = []
        maps = []
        for name, value in (("a.so", b"a"), ("b.so", b"b")):
            path = native / name
            path.write_bytes(value)
            records.append({"path": str(path), "sha256": gate_c.sha256_file(path)})
            maps.append(f"1000-2000 r-xp 00000000 00:00 1 {path}")
        inventory = root / "inventory.json"
        inventory.write_text(json.dumps({"host_native_extractions": records}), encoding="utf-8")
        maps_path = root / "maps.txt"
        maps_path.write_text("\n".join(maps), encoding="utf-8")
        traces = root / "traces"
        traces.mkdir()
        executables = {}
        for name in ("setpriv", "env", "java"):
            path = root / name
            path.write_bytes(name.encode())
            executables[name] = path
        rendered = trace.format(
            SETPRIV=executables["setpriv"], ENV=executables["env"], JAVA=executables["java"]
        )
        (traces / "trace.1").write_text(rendered, encoding="utf-8")
        supervisor = root / "supervisor.txt"
        supervisor.write_text(
            "trace_supervisor_uid=0\n"
            "tracee_uids_observed=1000,1000,1000,1000\n"
            "tracee_gids_observed=1000,1000,1000,1000\n"
            "tracee_pid=123\n"
            "no_new_privs_observed=1\n"
            "supplementary_groups_observed=NONE\n"
            f"setpriv_path={executables['setpriv']}\n"
            f"env_path={executables['env']}\n"
            f"java_path={executables['java']}\n",
            encoding="utf-8",
        )
        return root, inventory, maps_path, traces, supervisor

    def test_runtime_observation_accepts_one_java_exec_and_no_network(self):
        root, inventory, maps, traces, supervisor = self.runtime_fixture(self.EXEC_CHAIN)
        result = gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")
        self.assertFalse(result["child_process_spawned"])
        self.assertFalse(result["network_syscall_attempted"])
        self.assertFalse(result["acquisition_authorized"])

    def test_runtime_observation_rejects_child_exec(self):
        root, inventory, maps, traces, supervisor = self.runtime_fixture(
            self.EXEC_CHAIN + 'execve("/bin/sh", ["sh"], 0) = 0\n'
        )
        with self.assertRaises(gate_c.GateCError):
            gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")

    def test_runtime_observation_rejects_wrong_or_reordered_exec_chain(self):
        bad_chains = (
            self.EXEC_CHAIN.replace('execve("{JAVA}"', 'execve("/bin/sh"'),
            self.EXEC_CHAIN.replace("{SETPRIV}", "{TEMP}")
            .replace("{ENV}", "{SETPRIV}")
            .replace("{TEMP}", "{ENV}"),
            self.EXEC_CHAIN + 'execve("/missing", ["missing"], 0) = -1 ENOENT\n',
            self.EXEC_CHAIN.rsplit(" = 0", 1)[0] + " = -1 EACCES\n",
        )
        for chain in bad_chains:
            with self.subTest(chain=chain[-120:]):
                root, inventory, maps, traces, supervisor = self.runtime_fixture(chain)
                with self.assertRaises(gate_c.GateCError):
                    gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")

    def test_runtime_observation_rejects_truncated_java_argv(self):
        truncated = self.EXEC_CHAIN.replace(
            "org.phase9.gatec.GateCNativeMapProbe", "org.phase9.gatec.GateCNativeMap..."
        )
        root, inventory, maps, traces, supervisor = self.runtime_fixture(truncated)
        with self.assertRaises(gate_c.GateCError):
            gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")

    def test_runtime_observation_reports_only_missing_setpriv_argument_names(self):
        incomplete = self.EXEC_CHAIN.replace('"--clear-groups", ', "")
        root, inventory, maps, traces, supervisor = self.runtime_fixture(incomplete)
        with self.assertRaisesRegex(
            gate_c.GateCError,
            r"setpriv launcher arguments are incomplete: --clear-groups$",
        ):
            gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")

    def test_runtime_observation_accepts_abbreviated_setpriv_argv_with_kernel_postconditions(self):
        abbreviated = self.EXEC_CHAIN.replace(
            '["setpriv", "--reuid=1000", "--regid=1000", "--clear-groups", "--no-new-privs"]',
            "[...]",
        )
        root, inventory, maps, traces, supervisor = self.runtime_fixture(abbreviated)
        result = gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")
        self.assertEqual(
            result["setpriv_argv_observation"],
            "STRACE_ABBREVIATED_KERNEL_POSTCONDITIONS_VERIFIED",
        )

    def test_runtime_observation_rejects_incomplete_kernel_identity_postconditions(self):
        abbreviated = self.EXEC_CHAIN.replace(
            '["setpriv", "--reuid=1000", "--regid=1000", "--clear-groups", "--no-new-privs"]',
            "[...]",
        )
        root, inventory, maps, traces, supervisor = self.runtime_fixture(abbreviated)
        text = supervisor.read_text(encoding="utf-8").replace(
            "tracee_uids_observed=1000,1000,1000,1000",
            "tracee_uids_observed=1000,1000,0,1000",
        )
        supervisor.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(gate_c.GateCError, "privilege boundary mismatch"):
            gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")

    def test_runtime_observation_rejects_abbreviation_marker_outside_argv(self):
        misplaced = self.EXEC_CHAIN.replace(
            '["setpriv", "--reuid=1000", "--regid=1000", "--clear-groups", "--no-new-privs"]',
            '["setpriv"]',
        ) + "unrelated [...]\n"
        root, inventory, maps, traces, supervisor = self.runtime_fixture(misplaced)
        with self.assertRaisesRegex(gate_c.GateCError, "setpriv launcher arguments are incomplete"):
            gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")

    def test_runtime_observation_rejects_fork_without_exec(self):
        root, inventory, maps, traces, supervisor = self.runtime_fixture(
            self.EXEC_CHAIN + 'fork() = 123\n'
        )
        with self.assertRaises(gate_c.GateCError):
            gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")

    def test_runtime_observation_allows_thread_clone_only(self):
        root, inventory, maps, traces, supervisor = self.runtime_fixture(
            self.EXEC_CHAIN + 'clone(flags=CLONE_VM|CLONE_THREAD) = 123\n'
        )
        result = gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")
        self.assertEqual(result["thread_clone_count"], 1)
        self.assertFalse(result["child_process_spawned"])

    def test_runtime_observation_rejects_network_syscall(self):
        for call in (
            "socket(AF_INET, SOCK_STREAM, 0)",
            "socketpair(AF_UNIX, SOCK_STREAM, 0, [3, 4])",
            "bind(3, NULL, 0)",
            "listen(3, 1)",
            "accept4(3, NULL, NULL, 0)",
            "sendmmsg(3, [], 0, 0)",
            "recvmmsg(3, [], 0, 0, NULL)",
            "setsockopt(3, 1, 2, NULL, 0)",
        ):
            with self.subTest(call=call):
                root, inventory, maps, traces, supervisor = self.runtime_fixture(
                    self.EXEC_CHAIN + f'{call} = -1 EPERM\n'
                )
                with self.assertRaises(gate_c.GateCError):
                    gate_c.validate_runtime(inventory, maps, traces, supervisor, root / "output.json")


if __name__ == "__main__":
    unittest.main()
