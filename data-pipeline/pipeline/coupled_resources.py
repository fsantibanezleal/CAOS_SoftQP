"""Process RSS supervision, isolated from the historical scientific campaign."""

import ctypes
import os
from pathlib import Path


def process_memory(pid):
    if os.name == 'nt':
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                    'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        inspect = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
        inspect.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), 'Cannot inspect coupled worker memory')
        try:
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            if not inspect(handle, ctypes.byref(counters), counters.cb):
                raise OSError(ctypes.get_last_error(), 'Cannot read coupled worker RSS')
            return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
        finally:
            kernel.CloseHandle(handle)
    fields = {}
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:')):
            key, value, _ = line.split()
            fields[key.rstrip(':')] = int(value)*1024
    return fields['VmRSS'], fields['VmHWM']
