"""Exact inventories for the separate Windows scientific runtime."""
from __future__ import annotations

from contextlib import ExitStack
import ctypes
from ctypes import wintypes
from functools import lru_cache
import hashlib
import json
import os
import sys
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def path_key(path):
    return str(Path(path).resolve(strict=True)).casefold()


def regular_tree(root, *, kinds, directories=None):
    """Inventory exactly the approved Windows roots and reject reparse aliases."""
    def visit(folder):
        if directories is not None:
            directories.add(folder)
        for item in sorted(folder.iterdir()):
            relative = item.relative_to(root)
            if kinds == "base" and relative.parts[:2] == ("Lib", "site-packages"):
                continue
            info = item.lstat()
            require(not getattr(info, "st_file_attributes", 0) & 0x400,
                    f"reparse path in {kinds}: {relative.as_posix()}")
            # CPython's existing cache is outside the admitted import route.
            if kinds == "base" and (item.name == "__pycache__" or item.suffix == ".pyc"):
                continue
            if item.is_dir():
                yield from visit(item)
            else:
                require(item.is_file(), f"nonregular file in {kinds}: {relative.as_posix()}")
                yield relative.as_posix(), item
    if directories is not None:
        directories.add(root)
    if kinds == "base":
        for item in sorted(root.iterdir()):
            if item.parts[-1] in ("Lib", "DLLs"):
                require(not getattr(item.lstat(), "st_file_attributes", 0) & 0x400, "base reparse")
                yield from visit(item)
            elif item.suffix.lower() in (".dll", ".exe", ".zip", "._pth"):
                require(item.is_file() and not getattr(item.lstat(), "st_file_attributes", 0) & 0x400,
                        "invalid base program file")
                yield item.name, item
    else:
        yield from visit(root)


def read_identity(handle):
    digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return [os.fstat(handle.fileno()).st_size, digest]


def inventory(root, kind):
    output = {}
    for rel, path in regular_tree(root, kinds=kind):
        with path.open("rb") as handle:
            output[rel] = read_identity(handle)
    return output


@lru_cache(maxsize=1)
def windows_files():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    return api


def hold_handle(path, *, directory=False):
    api = windows_files()
    flags = 0x00200000 | (0x02000000 if directory else 0)
    handle = api.CreateFileW(str(path), 0x80000000, 1, None, 3, flags, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), f"Cannot establish write/delete custody: {path}")
    return handle


class HeldInventory:
    def __init__(self):
        self.stack = ExitStack()
        self.bound = {}
        self.roots = {}

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return self.stack.__exit__(*exception)

    def check(self, root, kind, expected, *, selected=False, hold_directories=True):
        directories = set()
        if selected:
            files = {}
            for rel in expected:
                relative = Path(rel)
                require(not relative.is_absolute() and ".." not in relative.parts, "invalid selected source path")
                path = root / relative
                require(path.resolve(strict=True).parts == path.parts and path.is_file(), "unavailable source path")
                for node in (path, *path.parents):
                    if node == root.parent:
                        break
                    require(not getattr(node.lstat(), "st_file_attributes", 0) & 0x400, "source reparse refused")
                    if node != path:
                        directories.add(node)
                files[rel] = path
        else:
            files = dict(regular_tree(root, kinds=kind, directories=directories))
        if hold_directories:
            for directory in sorted(directories):
                handle = hold_handle(directory, directory=True)
                self.stack.callback(windows_files().CloseHandle, handle)
        require(files.keys() == expected.keys(), f"{kind} inventory differs")
        for index, (rel, path) in enumerate(files.items(), 1):
            lock = hold_handle(path)
            self.stack.callback(windows_files().CloseHandle, lock)
            # Keep the kernel handle, not a CRT file descriptor. Windows' CRT
            # caps simultaneous descriptors below the approved file count.
            with path.open("rb") as handle:
                require(read_identity(handle) == expected[rel], f"{kind} file identity differs: {rel}")
                facts = os.fstat(handle.fileno())
            key = str(path).casefold()
            require(key not in self.bound, f"duplicate custody path: {path}")
            self.bound[key] = (kind, rel, expected[rel], (facts.st_dev, facts.st_ino))
            if index % 1000 == 0:
                print(f"Verified and held {kind} files {index}/{len(files)}", file=sys.stderr)
        if not selected:
            self.roots[kind] = (root, files.keys())

    def recheck_names(self):
        for kind, (root, keys) in self.roots.items():
            require(dict(regular_tree(root, kinds=kind)).keys() == keys, f"{kind} inventory changed")

    def identify(self, path):
        result = self.bound.get(path_key(path))
        require(result is not None, f"unadmitted origin: {path}")
        current = Path(path).stat()
        require((current.st_dev, current.st_ino) == result[3], f"live origin inode changed: {path}")
        return result[:3]
