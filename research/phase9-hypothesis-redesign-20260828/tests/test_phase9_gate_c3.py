from __future__ import annotations

import importlib.util
import os
import stat
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


custody = load_module("phase9_ephemeral_custody", ROOT / "runner/phase9_ephemeral_custody.py")


class GateC3EnvelopeTests(unittest.TestCase):
    def test_seccomp_launcher_blocks_process_and_network_but_allows_threads(self):
        source = ROOT / "runner/phase9_gate_c3_seccomp.c"
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "guard"
            build = subprocess.run(
                [
                    "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                    str(source), "-o", str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            probe = subprocess.run([str(binary), "--self-test"], capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(probe.stdout, "phase9_gate_c3_seccomp_self_test=PASS\n")
            socket_stdout_left, socket_stdout_right = socket.socketpair()
            try:
                socket_stdio = subprocess.run(
                    [str(binary), "--", "/bin/true"], stdout=socket_stdout_right,
                    stderr=subprocess.PIPE, text=True,
                )
                self.assertEqual(socket_stdio.returncode, 75, socket_stdio.stderr)
            finally:
                socket_stdout_left.close()
                socket_stdout_right.close()
            launch = subprocess.run([str(binary), "--", "/bin/true"], capture_output=True, text=True)
            if launch.returncode == 85 and "Landlock ABI unavailable" in launch.stderr:
                self.skipTest("local kernel does not expose Landlock; GitHub Gate C3 requires it")
            self.assertEqual(launch.returncode, 0, launch.stderr)
            second_exec = subprocess.run(
                [str(binary), "--", "/bin/sh", "-c", "exec /bin/true"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(second_exec.returncode, 0, second_exec.stderr)
            left, right = socket.socketpair()
            try:
                inherited = subprocess.run(
                    [
                        str(binary), "--", sys.executable, "-c",
                        "import os,sys; fd=int(sys.argv[1]); "
                        "\ntry: os.fstat(fd)"
                        "\nexcept OSError: raise SystemExit(0)"
                        "\nraise SystemExit(1)",
                        str(right.fileno()),
                    ],
                    pass_fds=(right.fileno(),), capture_output=True, text=True,
                )
                self.assertEqual(inherited.returncode, 0, inherited.stderr)
            finally:
                left.close()
                right.close()

    def test_seccomp_source_has_kernel_level_nonthread_and_egress_denials(self):
        source = (ROOT / "runner/phase9_gate_c3_seccomp.c").read_text(encoding="utf-8")
        for required in (
            "PR_SET_NO_NEW_PRIVS", "PR_SET_SECCOMP", "SECCOMP_MODE_FILTER",
            "__NR_fork", "__NR_vfork", "__NR_clone3", "__NR_clone",
            "0x00010000U", "__NR_connect", "__NR_sendto", "__NR_sendmsg",
            "__NR_sendmmsg", "__NR_io_uring_setup", "__NR_execveat",
            "__NR_close_range", "S_ISSOCK",
            "LANDLOCK_ACCESS_FS_EXECUTE", "landlock_restrict_self", "0x40000000U",
        ):
            self.assertIn(required, source)

    def test_prepare_creates_new_private_sibling_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            paths = custody.prepare(temp, "123", "1")
            self.assertEqual(paths["root"].parent, temp.resolve())
            self.assertEqual(set(paths) - {"root"}, set(custody.DIRECTORIES))
            for path in paths.values():
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
                self.assertEqual(path.stat().st_uid, os.getuid())

    def test_prepare_rejects_reuse_and_non_decimal_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            custody.prepare(temp, "123", "1")
            with self.assertRaises(custody.CustodyError):
                custody.prepare(temp, "123", "1")
            with self.assertRaises(custody.CustodyError):
                custody.prepare(temp, "../123", "1")

    def test_prepare_rejects_writable_or_symlinked_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            os.chmod(temp, 0o777)
            with self.assertRaises(custody.CustodyError):
                custody.prepare(temp, "123", "1")
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            actual = parent / "actual"
            actual.mkdir(mode=0o700)
            alias = parent / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            with self.assertRaises(custody.CustodyError):
                custody.prepare(alias, "123", "1")
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            writable = parent / "writable"
            writable.mkdir(mode=0o700)
            private = writable / "private"
            private.mkdir(mode=0o700)
            os.chmod(writable, 0o777)
            with self.assertRaises(custody.CustodyError):
                custody.prepare(private, "123", "1")

    def test_private_tree_rejects_symlink_hardlink_fifo_and_open_mode(self):
        mutations = ("symlink", "hardlink", "fifo", "mode")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                paths = custody.prepare(Path(directory), "123", "1")
                raw = paths["raw"]
                target = raw / "a.csv"
                target.write_bytes(b"x")
                os.chmod(target, 0o600)
                if mutation == "symlink":
                    (raw / "link.csv").symlink_to(target)
                elif mutation == "hardlink":
                    os.link(target, raw / "hard.csv")
                elif mutation == "fifo":
                    os.mkfifo(raw / "pipe")
                else:
                    os.chmod(target, 0o644)
                with self.assertRaises(custody.CustodyError):
                    custody.validate_private_tree(raw)

    def test_exact_raw_allowlist_rejects_missing_extra_and_duplicate_inode(self):
        expected = list(custody.CANONICAL_RAW_NAMES)
        with tempfile.TemporaryDirectory() as directory:
            paths = custody.prepare(Path(directory), "123", "1")
            raw = paths["raw"]
            for name in expected:
                path = raw / name
                path.write_bytes(b"x")
                os.chmod(path, 0o600)
            self.assertEqual(custody.validate_exact_raw_files(raw, expected)["file_count"], 48)
            (raw / expected[-1]).unlink()
            with self.assertRaises(custody.CustodyError):
                custody.validate_exact_raw_files(raw, expected)
        with tempfile.TemporaryDirectory() as directory:
            paths = custody.prepare(Path(directory), "123", "1")
            raw = paths["raw"]
            for name in expected:
                path = raw / name
                path.write_bytes(b"x")
                os.chmod(path, 0o600)
            extra = raw / "EXTRA.csv"
            extra.write_bytes(b"x")
            os.chmod(extra, 0o600)
            with self.assertRaises(custody.CustodyError):
                custody.validate_exact_raw_files(raw)
        with tempfile.TemporaryDirectory() as directory:
            paths = custody.prepare(Path(directory), "123", "1")
            raw = paths["raw"]
            for name in expected:
                path = raw / name
                path.write_bytes(b"x")
                os.chmod(path, 0o600)
            os.link(raw / expected[0], raw / "duplicate.csv")
            with self.assertRaises(custody.CustodyError):
                custody.validate_private_tree(raw)
        with self.assertRaises(custody.CustodyError):
            custody.validate_exact_raw_files(Path("/unused"), [f"S{index:02d}.csv" for index in range(48)])

    def test_exact_raw_allowlist_detects_name_swap_during_validation(self):
        expected = list(custody.CANONICAL_RAW_NAMES)
        with tempfile.TemporaryDirectory() as directory:
            raw = custody.prepare(Path(directory), "123", "1")["raw"]
            for name in expected:
                path = raw / name
                path.write_bytes(b"x")
                os.chmod(path, 0o600)
            original_listdir = os.listdir
            swapped = False

            def swap_after_snapshot(descriptor):
                nonlocal swapped
                names = original_listdir(descriptor)
                if not swapped and isinstance(descriptor, int):
                    swapped = True
                    (raw / expected[0]).unlink()
                    extra = raw / "EXTRA.csv"
                    extra.write_bytes(b"x")
                    os.chmod(extra, 0o600)
                return names

            with mock.patch.object(custody.os, "listdir", side_effect=swap_after_snapshot):
                with self.assertRaises(custody.CustodyError):
                    custody.validate_exact_raw_files(raw)

    def test_removal_is_scoped_and_records_no_secure_erase_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            paths = custody.prepare(temp, "123", "1")
            private = paths["cache"] / "cache.bin"
            private.write_bytes(b"private")
            os.chmod(private, 0o600)
            proof = custody.remove_private_tree(paths["root"], temp)
            self.assertFalse(paths["root"].exists())
            self.assertFalse(proof["post_delete_exists"])
            self.assertTrue(proof["logical_removal_only_secure_erase_not_claimed"])
            with self.assertRaises(custody.CustodyError):
                custody.remove_private_tree(temp, temp.parent)
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            unrelated = temp / "phase9-custody-unrelated-backup"
            unrelated.mkdir(mode=0o700)
            with self.assertRaises(custody.CustodyError):
                custody.remove_private_tree(unrelated, temp)
            self.assertTrue(unrelated.is_dir())


if __name__ == "__main__":
    unittest.main()
