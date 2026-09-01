#!/usr/bin/env python3
"""Fail-closed same-run ephemeral custody primitives; never reads market values."""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path


DIRECTORIES = ("raw", "cache", "qc-private", "metadata-private", "upload-staging")
INSTRUMENTS = (
    "AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY",
    "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD",
)
CANONICAL_RAW_NAMES = tuple(
    f"{instrument}_{timeframe}_{side}.csv"
    for instrument in INSTRUMENTS
    for timeframe in ("M15", "H1")
    for side in ("bid", "ask")
)
_PREPARED_ROOTS: dict[str, tuple[int, int]] = {}


class CustodyError(ValueError):
    pass


def _require_owned_private_directory(path: Path, label: str) -> os.stat_result:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise CustodyError(f"{label} must be a real directory")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise CustodyError(f"{label} must be owned by the runner with mode 0700")
    return info


def _require_canonical_safe_temp(path: Path) -> Path:
    if not path.is_absolute():
        raise CustodyError("RUNNER_TEMP must be absolute")
    canonical = path.resolve(strict=True)
    if path != canonical:
        raise CustodyError("RUNNER_TEMP must not contain symlink components")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise CustodyError("RUNNER_TEMP must be a runner-owned directory")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise CustodyError("RUNNER_TEMP must not be group/world writable")
    current = path
    while current != current.parent:
        component = current.lstat()
        if current.is_symlink():
            raise CustodyError("RUNNER_TEMP path components must not be symlinks")
        if stat.S_IMODE(component.st_mode) & 0o022:
            raise CustodyError("RUNNER_TEMP ancestors must not be group/world writable")
        current = current.parent
    return canonical


def prepare(runner_temp: Path, run_id: str, run_attempt: str) -> dict[str, Path]:
    if re.fullmatch(r"[0-9]+", run_id) is None or re.fullmatch(r"[0-9]+", run_attempt) is None:
        raise CustodyError("Run identity must be decimal")
    temp = _require_canonical_safe_temp(runner_temp)
    root = temp / f"phase9-custody-{run_id}-{run_attempt}"
    if root.exists() or root.is_symlink():
        raise CustodyError("Custody root must be new")
    temp_fd = os.open(temp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    previous_umask = os.umask(0o077)
    try:
        os.mkdir(root.name, mode=0o700, dir_fd=temp_fd)
        root_fd = os.open(root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=temp_fd)
        paths = {name: root / name for name in DIRECTORIES}
        try:
            for name in DIRECTORIES:
                os.mkdir(name, mode=0o700, dir_fd=root_fd)
        finally:
            os.close(root_fd)
    except BaseException:
        try:
            os.stat(root.name, dir_fd=temp_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            shutil.rmtree(root.name, dir_fd=temp_fd)
        raise
    finally:
        os.umask(previous_umask)
        os.close(temp_fd)
    _require_owned_private_directory(root, "Custody root")
    root_info = root.lstat()
    _PREPARED_ROOTS[str(root)] = (root_info.st_dev, root_info.st_ino)
    for name, path in paths.items():
        _require_owned_private_directory(path, f"Custody {name}")
        if path.parent != root:
            raise CustodyError("Custody directories must be direct siblings")
    if len({path.stat().st_ino for path in paths.values()}) != len(paths):
        raise CustodyError("Custody directory inode collision")
    return {"root": root, **paths}


def _validate_tree_fd(root_fd: int, allow_directories: bool) -> tuple[dict[str, int], set[str]]:
    file_inodes: set[tuple[int, int]] = set()
    file_count = 0
    directory_count = 1
    byte_count = 0
    visited: set[str] = set()
    for directory, names, files, dir_fd in os.fwalk(".", topdown=True, follow_symlinks=False, dir_fd=root_fd):
        for name in sorted(names):
            visited.add(name if directory == "." else str(Path(directory) / name))
            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                raise CustodyError(f"Symlink or non-directory in private tree: {name}")
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700 or not allow_directories:
                raise CustodyError(f"Unsafe private directory: {name}")
            directory_count += 1
        for name in sorted(files):
            visited.add(name if directory == "." else str(Path(directory) / name))
            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            if info.st_uid != os.getuid():
                raise CustodyError(f"Foreign-owned private tree entry: {name}")
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise CustodyError(f"Private file must be single-link regular: {name}")
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise CustodyError(f"Private file mode must be 0600: {name}")
            identity = (info.st_dev, info.st_ino)
            if identity in file_inodes:
                raise CustodyError(f"Duplicate private file inode: {name}")
            file_inodes.add(identity)
            file_count += 1
            byte_count += info.st_size
    return ({"file_count": file_count, "directory_count": directory_count, "byte_count": byte_count}, visited)


def validate_private_tree(root: Path, allow_directories: bool = True) -> dict[str, int]:
    initial = _require_owned_private_directory(root, "Private tree root")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        pinned = os.fstat(root_fd)
        if (pinned.st_dev, pinned.st_ino) != (initial.st_dev, initial.st_ino):
            raise CustodyError("Private tree changed while it was opened")
        return _validate_tree_fd(root_fd, allow_directories)[0]
    finally:
        os.close(root_fd)


def validate_exact_raw_files(raw: Path, expected_names: list[str] | None = None) -> dict[str, int]:
    canonical = list(CANONICAL_RAW_NAMES)
    if expected_names is not None and expected_names != canonical:
        raise CustodyError("Caller raw allowlist differs from the frozen canonical 48-series set")
    expected_names = canonical
    if len({name.casefold() for name in expected_names}) != 48:
        raise CustodyError("Raw allowlist contains a case collision")
    initial = _require_owned_private_directory(raw, "Raw root")
    raw_fd = os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        pinned = os.fstat(raw_fd)
        if (pinned.st_dev, pinned.st_ino) != (initial.st_dev, initial.st_ino):
            raise CustodyError("Raw root changed while it was opened")
        names = os.listdir(raw_fd)
        if len(names) != 48 or set(names) != set(expected_names):
            raise CustodyError("Raw file set differs from the exact 48-file allowlist")
        if len({name.casefold() for name in names}) != 48:
            raise CustodyError("Raw file set contains a case collision")
        result, visited = _validate_tree_fd(raw_fd, allow_directories=False)
        if visited != set(expected_names) or set(os.listdir(raw_fd)) != set(expected_names):
            raise CustodyError("Raw file set changed during validation")
        return result
    finally:
        os.close(raw_fd)


def _remove_contents_fd(directory_fd: int) -> None:
    for name in os.listdir(directory_fd):
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                _remove_contents_fd(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        elif stat.S_ISREG(info.st_mode):
            os.unlink(name, dir_fd=directory_fd)
        else:
            raise CustodyError("Unsafe entry appeared during custody removal")


def remove_private_tree(root: Path, runner_temp: Path) -> dict[str, object]:
    temp = _require_canonical_safe_temp(runner_temp)
    if not root.is_absolute() or root.parent != temp or not root.name.startswith("phase9-custody-"):
        raise CustodyError("Refusing to remove a non-custody path")
    expected_identity = _PREPARED_ROOTS.get(str(root))
    if expected_identity is None:
        raise CustodyError("Custody root was not prepared by this process")
    parent_fd = os.open(temp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before_delete = os.stat(root.name, dir_fd=parent_fd, follow_symlinks=False)
        if (before_delete.st_dev, before_delete.st_ino) != expected_identity or not stat.S_ISDIR(before_delete.st_mode):
            raise CustodyError("Custody root changed before removal")
        root_fd = os.open(root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            pinned = os.fstat(root_fd)
            if (pinned.st_dev, pinned.st_ino) != expected_identity:
                raise CustodyError("Custody root changed while it was opened for removal")
            before = _validate_tree_fd(root_fd, allow_directories=True)[0]
            _remove_contents_fd(root_fd)
        finally:
            os.close(root_fd)
        final_identity = os.stat(root.name, dir_fd=parent_fd, follow_symlinks=False)
        if (final_identity.st_dev, final_identity.st_ino) != expected_identity:
            raise CustodyError("Custody root changed before final directory removal")
        os.rmdir(root.name, dir_fd=parent_fd)
        try:
            os.stat(root.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise CustodyError("Custody root still exists after removal")
    finally:
        os.close(parent_fd)
    del _PREPARED_ROOTS[str(root)]
    return {
        "pre_delete_file_count": before["file_count"],
        "pre_delete_directory_count": before["directory_count"],
        "pre_delete_byte_count": before["byte_count"],
        "post_delete_exists": False,
        "logical_removal_only_secure_erase_not_claimed": True,
    }
