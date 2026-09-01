#!/usr/bin/env python3
"""Pinned private custody for metadata-only local/synthetic evidence."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path


DIRECTORIES = ("cache", "evidence", "home", "tmp")
_PREPARED_ROOTS: dict[str, tuple[int, int]] = {}


class CustodyError(RuntimeError):
    pass


def _private_directory(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as failure:
        raise CustodyError(f"Cannot inspect private directory: {path}") from failure
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise CustodyError(f"Not a real directory: {path}")
    if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise CustodyError(f"Directory is not private: {path}")
    return info


def _validated_directory(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    _private_directory(absolute)
    resolved = absolute.resolve(strict=True)
    if resolved != absolute:
        raise CustodyError(f"Symlink component rejected: {absolute}")
    return absolute


def _validate_tree_fd(root_fd: int) -> dict[str, int]:
    identities: set[tuple[int, int]] = set()
    directories = 1
    files = 0
    for _, names, file_names, directory_fd in os.fwalk(
            ".", topdown=True, follow_symlinks=False, dir_fd=root_fd):
        for name in sorted(names):
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise CustodyError(f"Unsafe private directory: {name}")
            identity = (info.st_dev, info.st_ino)
            if identity in identities:
                raise CustodyError(f"Duplicate inode rejected: {name}")
            identities.add(identity)
            directories += 1
        for name in sorted(file_names):
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise CustodyError(f"File custody failed: {name}")
            identity = (info.st_dev, info.st_ino)
            if identity in identities:
                raise CustodyError(f"Duplicate inode rejected: {name}")
            identities.add(identity)
            files += 1
    return {"directory_count": directories, "file_count": files}


def _remove_contents_fd(directory_fd: int) -> None:
    for name in os.listdir(directory_fd):
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child_fd = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            try:
                _remove_contents_fd(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        elif stat.S_ISREG(info.st_mode):
            os.unlink(name, dir_fd=directory_fd)
        else:
            raise CustodyError("Unsafe entry appeared during custody removal")


def prepare(anchor: Path, run_id: str, run_attempt: str) -> dict[str, Path]:
    if re.fullmatch(r"[0-9]+", run_id) is None or re.fullmatch(r"[0-9]+", run_attempt) is None:
        raise CustodyError("Run identity must be decimal")
    anchor = _validated_directory(anchor)
    root = anchor / f"phase9-metadata-{run_id}-{run_attempt}"
    if os.path.lexists(root):
        raise CustodyError("Metadata custody root must be new")
    anchor_info = _private_directory(anchor)
    anchor_fd = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    pinned_anchor = os.fstat(anchor_fd)
    if (pinned_anchor.st_dev, pinned_anchor.st_ino) != (anchor_info.st_dev, anchor_info.st_ino):
        os.close(anchor_fd)
        raise CustodyError("Metadata custody anchor changed while it was opened")
    previous_umask = os.umask(0o077)
    try:
        os.mkdir(root.name, mode=0o700, dir_fd=anchor_fd)
        root_fd = os.open(
            root.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=anchor_fd,
        )
        try:
            for name in DIRECTORIES:
                os.mkdir(name, mode=0o700, dir_fd=root_fd)
        except BaseException:
            _remove_contents_fd(root_fd)
            raise
        finally:
            os.close(root_fd)
    except BaseException:
        try:
            info = os.stat(root.name, dir_fd=anchor_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISDIR(info.st_mode):
                os.rmdir(root.name, dir_fd=anchor_fd)
        raise
    finally:
        os.umask(previous_umask)
        os.close(anchor_fd)
    root_info = _private_directory(root)
    paths = {"root": root, **{name: root / name for name in DIRECTORIES}}
    validate_private_tree(root)
    _PREPARED_ROOTS[str(root)] = (root_info.st_dev, root_info.st_ino)
    return paths


def validate_private_tree(root: Path) -> dict[str, int]:
    root = _validated_directory(root)
    initial = _private_directory(root)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        pinned = os.fstat(root_fd)
        if (pinned.st_dev, pinned.st_ino) != (initial.st_dev, initial.st_ino):
            raise CustodyError("Private tree changed while it was opened")
        return _validate_tree_fd(root_fd)
    finally:
        os.close(root_fd)


def remove(root: Path, anchor: Path) -> dict[str, bool]:
    anchor = _validated_directory(anchor)
    root = Path(os.path.abspath(root))
    if root.parent != anchor or not root.name.startswith("phase9-metadata-"):
        raise CustodyError("Cleanup target is outside the exact metadata custody scope")
    expected = _PREPARED_ROOTS.get(str(root))
    if expected is None:
        raise CustodyError("Metadata custody root was not prepared by this process")
    anchor_fd = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before = os.stat(root.name, dir_fd=anchor_fd, follow_symlinks=False)
        if (before.st_dev, before.st_ino) != expected or not stat.S_ISDIR(before.st_mode):
            raise CustodyError("Metadata custody root changed before removal")
        root_fd = os.open(
            root.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=anchor_fd,
        )
        try:
            pinned = os.fstat(root_fd)
            if (pinned.st_dev, pinned.st_ino) != expected:
                raise CustodyError("Metadata custody root changed while opening")
            _validate_tree_fd(root_fd)
            _remove_contents_fd(root_fd)
        finally:
            os.close(root_fd)
        final = os.stat(root.name, dir_fd=anchor_fd, follow_symlinks=False)
        if (final.st_dev, final.st_ino) != expected:
            raise CustodyError("Metadata custody root changed before final removal")
        os.rmdir(root.name, dir_fd=anchor_fd)
        try:
            os.stat(root.name, dir_fd=anchor_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise CustodyError("Metadata custody root still exists after removal")
    finally:
        os.close(anchor_fd)
    del _PREPARED_ROOTS[str(root)]
    return {
        "post_delete_exists": False,
        "logical_removal_only_secure_erase_not_claimed": True,
    }
