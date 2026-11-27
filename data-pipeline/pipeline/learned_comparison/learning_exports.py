"""Fixed registered learning exports and final result receipts."""

from contextlib import contextmanager
from pathlib import Path

from . import contracts as c
from . import evaluation_models as models

RESULT = "softqp.r4.learning-result/2"
_METADATA_RESERVE = 128 * 2**20


@contextmanager
def export_lease(root):
    import msvcrt

    lease = root / ".learning-publication.lock"
    if lease.exists():
        models.t.phase._path_stat(lease)
    with lease.open("a+b") as handle:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        yield


def validate_preprocessing(root, digest, frozen, *, context):
    _, _, payload, ids = models._selected(
        frozen.root,
        expected_frozen=frozen.sha256,
        expected_run=frozen.document["run_sha256"],
        expected_checkpoint=frozen.document["checkpoint"]["sha256"],
        dependency_lock_sha256=context.dependency_lock_sha256,
        allow_fixture=context.allow_fixture,
    )
    doc = models._document(root, "preprocessing.json", digest)
    models._preprocessing(doc, payload, ids, context.authority)
    return doc


def _unavailable(names, reason):
    return {name: {"state": "unavailable", "ref": None, "reason": reason} for name in names}


def _available(directory, name, digest):
    return {
        "state": "available",
        "ref": {"path": f"{directory.name}/{name}", "sha256": digest},
        "reason": None,
    }


def export_training(root, key, run, *, plan, runtime, budget, require_live):
    names = ("frozen", "preprocessing")
    selected = run.document["checkpoints"].get("final")
    if selected is None or run.document["state"] not in ("completed", "fixture-exercise"):
        return _unavailable(names, "training did not produce a qualified selected checkpoint")
    frozen_root, prep_root = (root / f"{key}-{suffix}" for suffix in names)
    try:
        require_live()
        checkpoint = models.t._json_file(run.root, selected)["payload"]
        reserve = 2 * checkpoint["weights"]["byte_count"] + _METADATA_RESERVE
        budget.check(extra_bytes=reserve)
        c.ensure(
            not frozen_root.exists() and not prep_root.exists(), "learning export destination already exists"
        )
        frozen = models.t.publish_frozen_inference(run, frozen_root, expected_run_sha256=run.sha256)
        prep_root.mkdir()
        prep_sha = models.publish_preprocessing(
            prep_root,
            run_root=run.root,
            frozen_root=frozen_root,
            expected_run=run.sha256,
            expected_frozen=frozen.sha256,
            expected_checkpoint=selected["sha256"],
            plan=plan,
            runtime=runtime,
        )
        validate_preprocessing(prep_root, prep_sha, frozen, context=plan.context)
        budget.check()
        require_live()
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        return _unavailable(names, ("training projection failed: " + str(error))[:768])
    return {
        "frozen": _available(frozen_root, "frozen-inference.json", frozen.sha256),
        "preprocessing": _available(prep_root, "preprocessing.json", prep_sha),
    }


def export_calibration(
    root, key, calibration, *, plan, runtime, budget, require_live, preprocessing_root, preprocessing_sha256
):
    names = ("bundle",)
    if calibration["state"] not in ("calibrated", "not-applicable"):
        return _unavailable(names, "calibration did not produce an available disposition")
    bundle_root = root / f"{key}-bundle"
    cal_sha = c.digest(c.canonical_bytes(calibration))
    try:
        require_live()
        budget.check(extra_bytes=_METADATA_RESERVE)
        bundle_root.mkdir()
        sha = models.publish_bundle(
            bundle_root,
            preprocessing_root=preprocessing_root,
            calibration_root=root / key,
            expected_preprocessing=preprocessing_sha256,
            expected_calibration=cal_sha,
            plan=plan,
            runtime=runtime,
        )
        frozen = plan.frozen.document
        trust = models.ModelTrust(
            bundle_root,
            preprocessing_root,
            plan.frozen.root,
            sha,
            preprocessing_sha256,
            cal_sha,
            plan.expected_receipt_sha256,
            plan.expected_run_sha256,
            plan.expected_checkpoint_sha256,
            frozen["method"],
            frozen["seed"],
            frozen["protocol"]["sha256"],
            frozen["population_sha256"],
            frozen["preflight_sha256"],
            plan.context.dependency_lock_sha256,
        )
        models.read_bundle(trust, authority=plan.context.authority, allow_fixture=plan.context.allow_fixture)
        budget.check()
        require_live()
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        return _unavailable(names, ("calibration projection failed: " + str(error))[:768])
    return {"bundle": _available(bundle_root, "bundle.json", sha)}


def seal_result(job, result, *, require_live, budget):
    import os

    require_live()
    raw = c.canonical_bytes(result)
    budget.check(extra_bytes=2 * len(raw))
    job = models.t.phase._exact_directory(Path(job))
    marker = job / "learning-result.json"
    pending = marker.with_suffix(".json.pending")
    c.ensure(not marker.exists(), "learning result already exists")
    with pending.open("xb") as handle:
        identity = os.fstat(handle.fileno())
        try:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            _rollback_marker(pending, identity)
            raise
    try:
        pending.rename(marker)  # Windows rename refuses an existing destination.
    except BaseException:
        _rollback_marker(pending, identity)
        raise
    try:
        c.ensure(
            models._document(job, marker.name, c.digest(raw)) == result, "learning result changed on disk"
        )
        budget.check()
        require_live()
        c.ensure(
            os.path.samestat(identity, marker.lstat()), "learning result identity changed after publication"
        )
    except BaseException:
        _rollback_marker(marker, identity)
        raise
    return result


def _rollback_marker(path, identity):
    """Remove only our inode, holding a name-stable Windows handle for deletion."""
    import ctypes
    from ctypes import wintypes
    import msvcrt
    import os

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    delete_and_read_attributes = 0x10080
    share_read_write = 3  # Deliberately omit FILE_SHARE_DELETE.
    open_existing, open_reparse_point = 3, 0x00200000
    handle = kernel.CreateFileW(
        str(path), delete_and_read_attributes, share_read_write, None, open_existing, open_reparse_point, None
    )
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        if error in (2, 3):
            return
        raise ctypes.WinError(error)
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    try:
        if os.path.samestat(identity, os.fstat(fd)):
            delete = wintypes.BOOLEAN(1)
            if not kernel.SetFileInformationByHandle(handle, 4, ctypes.byref(delete), ctypes.sizeof(delete)):
                raise ctypes.WinError(ctypes.get_last_error())
    finally:
        os.close(fd)
