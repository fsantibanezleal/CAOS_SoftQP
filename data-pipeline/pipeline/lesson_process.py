"""Bounded, exclusively owned worker trees; no scientific method is implemented here."""

import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


class WorkerCleanupError(RuntimeError):
    """The caller must retain scratch evidence when owned teardown is uncertain."""


class WindowsJob:
    """Assign a suspended launcher before any descendant can escape ownership."""

    def __init__(self):
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [("per_process", ctypes.c_int64), ("per_job", ctypes.c_int64),
                        ("flags", w.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
                        ("active", w.DWORD), ("affinity", ctypes.c_size_t),
                        ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                        ("peak_job", ctypes.c_size_t)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                       w.DWORD, ctypes.c_void_p]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.name = "SoftQP-Lesson-" + uuid.uuid4().hex
        self.handle = self.api.CreateJobObjectW(None, self.name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def attach_and_resume(self, process):
        from ctypes import wintypes as w

        if not self.api.AssignProcessToJobObject(self.handle, w.HANDLE(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

        class ThreadEntry(ctypes.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("tid", w.DWORD),
                        ("owner", w.DWORD), ("base_priority", w.LONG),
                        ("delta_priority", w.LONG), ("flags", w.DWORD)]

        self.api.CreateToolhelp32Snapshot.restype = w.HANDLE
        self.api.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
        self.api.Thread32First.argtypes = [w.HANDLE, ctypes.POINTER(ThreadEntry)]
        self.api.Thread32Next.argtypes = [w.HANDLE, ctypes.POINTER(ThreadEntry)]
        self.api.OpenThread.restype = w.HANDLE
        self.api.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.api.ResumeThread.argtypes = [w.HANDLE]
        self.api.ResumeThread.restype = w.DWORD
        snapshot = self.api.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        found = False
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            more = self.api.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.owner == process.pid:
                    thread = self.api.OpenThread(2, False, entry.tid)
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if self.api.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                        found = True
                    finally:
                        self.api.CloseHandle(thread)
                more = self.api.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            self.api.CloseHandle(snapshot)
        if not found:
            raise RuntimeError("Suspended worker has no resumable initial thread")

    def close(self, deadline=None):
        if self.handle:
            from ctypes import wintypes as w

            class Accounting(ctypes.Structure):
                _fields_ = [(name, ctypes.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")]
                _fields_ += [(name, w.DWORD) for name in ("faults", "total", "active", "terminated")]

            handles = []
            try:
                class ProcessIds(ctypes.Structure):
                    _fields_ = [("assigned", w.DWORD), ("count", w.DWORD),
                                ("ids", ctypes.c_size_t * 4096)]

                ids = ProcessIds()
                if not self.api.QueryInformationJobObject(self.handle, 3, ctypes.byref(ids),
                                                          ctypes.sizeof(ids), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.api.OpenProcess.restype = w.HANDLE
                self.api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
                self.api.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
                for pid in ids.ids[:ids.count]:
                    handle = self.api.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
                    if handle:
                        handles.append(handle)
                if not self.api.TerminateJobObject(self.handle, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
                deadline = time.monotonic() + 3 if deadline is None else deadline
                while True:
                    info = Accounting()
                    if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info),
                                                              ctypes.sizeof(info), None):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if not info.active:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Owned lesson job cleanup exceeded3seconds")
                    time.sleep(0.01)
                for handle in handles:
                    remaining = max(0, int((deadline - time.monotonic()) * 1000))
                    if self.api.WaitForSingleObject(handle, remaining) != 0:
                        raise RuntimeError("Owned lesson descendant did not exit within cleanup deadline")
            finally:
                for handle in handles:
                    self.api.CloseHandle(handle)
                self.api.CloseHandle(self.handle)
                self.handle = None


def execute(command, request, scratch, env, *, timeout=30, limit=65536):
    """Spool capped files, never inherited pipes; clean the owned tree on all exits."""
    scratch = Path(scratch)
    paths = [scratch / name for name in ("input.json", "stdout.json", "stderr.txt")]
    paths[0].write_bytes(request)
    job, process = None, None
    try:
        if os.name == "nt":
            job = WindowsJob()
            env = {**env, "SOFTQP_LESSON_JOB": job.name}
        with paths[0].open("rb") as stdin, paths[1].open("wb") as stdout, paths[2].open("wb") as stderr:
            process = subprocess.Popen(command, stdin=stdin, stdout=stdout, stderr=stderr,
                                       cwd=scratch, env=env, start_new_session=os.name != "nt",
                                       creationflags=4 if os.name == "nt" else 0)
            if job:
                job.attach_and_resume(process)
            deadline = time.monotonic() + timeout
            while True:
                if any(path.stat().st_size > limit for path in paths[1:]):
                    raise ValueError("Lesson worker exceeded stdout/stderr limit")
                code = process.poll()
                if code is not None:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Lesson worker exceeded its execution deadline")
                time.sleep(0.01)
        if code:
            with paths[2].open("rb") as diagnostic:
                message = diagnostic.read(2000).decode("utf-8", errors="replace")
            raise RuntimeError(f"Lesson worker failed ({code}); bounded diagnostic: "
                               + message)
    finally:
        original = sys.exception()
        cleanup_errors = []
        deadline = time.monotonic() + 3
        if job:
            try:
                job.close(deadline=deadline)
            except Exception as error:
                cleanup_errors.append(error)
        if process is not None:
            try:
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()  # also attempt launcher cleanup after job teardown failed
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except Exception as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            message = "; ".join(str(error) for error in cleanup_errors)
            raise WorkerCleanupError(f"Owned worker cleanup uncertain: {message}; recovery directory: {scratch}") from original
    if any(path.stat().st_size > limit for path in paths[1:]):
        raise ValueError("Lesson worker exceeded stdout/stderr limit")
    return paths[1].read_bytes()
