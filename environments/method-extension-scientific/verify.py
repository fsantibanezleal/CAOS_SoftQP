"""Supervise exact installed-files, cold product imports and excluded SDK controls."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import importlib
from importlib.machinery import PathFinder, SourceFileLoader
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import ModuleType

LIMITS = {"scan": 600, "imports": 180, "reference": 30, "cold": 30, "gradient": 30, "reader": 30,
          "final": 30, "generate": 30}
RSS = 8 * 2**30
LEARNING_LIMIT = 48 * 3600


def require(predicate, reason):
    if not predicate:
        raise ValueError(reason)


def load(path, expected):
    from hashlib import sha256
    data = path.read_bytes()
    require(sha256(data).hexdigest() == expected, f"external byte identity differs: {path.name}")
    return data


def source_code(path, expected):
    scope = {"__name__": "qualified_scientific_source", "__file__": str(path)}
    exec(compile(load(path, expected), str(path), "exec", optimize=0), scope)
    return scope


def configuration(args):
    profile = json.loads(load(args.profile / "provenance.json", args.expected_profile_sha256))
    stamp = profile["scientific_runtime"]
    require(stamp["format"] == "softqp.product-runtime-custody/v1", "unsupported profile format")
    manifest = json.loads(load(args.profile / "custody.json", stamp["manifest_sha256"]))
    load(Path(__file__), stamp["verifier_sha256"])
    require(set(manifest) == {"runtime", "base", "source", "tools", "module_owners"},
            "incomplete runtime custody inventory")
    return profile, stamp, manifest


def launch_inputs(args, stamp):
    fields = (args.request, args.expected_request_sha256, args.policy, args.expected_policy_sha256)
    if not any(fields):
        require(not (getattr(args, "campaign", False) or getattr(args, "learning", False)),
                "registered dispatch requires governed launch inputs")
        return None
    require(all(fields), "request and policy require independently expected digests")
    require(stamp["source_kind"] == "committed-product-checkout",
            "qualification snapshot cannot dispatch registered generation")
    require(args.request != args.policy and max(args.request.stat().st_size, args.policy.stat().st_size) <= 65536,
            "registered dispatch input outside bounded size")
    return load(args.request, args.expected_request_sha256), load(args.policy, args.expected_policy_sha256)


def campaign_bounds(args, launch):
    raw, governance = launch
    request, policy = json.loads(raw), json.loads(governance)
    require(request["schema"] == "softqp.r4.generate-campaign-request/1" and
            policy["schema"] == "softqp.r4.generate-campaign-policy/1", "invalid fixed campaign request")
    root = Path(policy["approval"]["root"]).resolve(strict=True)
    def referenced(name):
        ref = policy[name]
        relative = Path(ref["path"])
        require(not relative.is_absolute() and ".." not in relative.parts, "unconfined governance reference")
        candidate = (root / relative).resolve(strict=True)
        require(candidate.is_relative_to(root) and candidate.is_file(), "unconfined governance file")
        require(candidate.stat().st_size < 2**24, "governance file exceeds bounded size")
        return json.loads(load(candidate, ref["sha256"]))
    require(request["plan_sha256"] == policy["plan"]["sha256"], "campaign plan digest differs")
    plan, frontier = referenced("plan"), referenced("frontier")
    entries = plan["entries"]
    first, end, seconds = frontier["next"], policy["end"], policy["max_wall_seconds"]
    require(plan["schema"] == "softqp.r4.generate-campaign-plan/1" and
            frontier["schema"] == "softqp.r4.generate-campaign-frontier/1" and
            frontier["plan_sha256"] == policy["plan"]["sha256"] and
            plan["profile_sha256"] == args.expected_profile_sha256 and
            all(type(item) is int for item in (first, end, seconds)) and
            0 <= first <= end <= len(entries) and 0 < seconds <= 86400,
            "bounded exact campaign plan or frontier differs")
    return first, end, seconds, entries


def write_marker(root, name, data):
    staged = root / (name + ".pending")
    staged.write_bytes(json.dumps(data, allow_nan=False, sort_keys=True).encode())
    staged.rename(root / name)


def read_marker(path):
    require(path.stat().st_size <= 8192, "oversize owned slot marker")
    with path.open("rb") as handle:
        raw = handle.read(8193)
    require(len(raw) <= 8192, "oversize owned slot marker")
    return json.loads(raw)


def dispatch_registered(args, stamp, held, raw, policy, violations):
    from hashlib import sha256
    head = subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD^{commit}"], timeout=10)
    require(head.decode().strip() == stamp["source_head"], "active committed product source differs")
    from pipeline.learned_comparison import generator
    custody = object()
    live = True
    pid = os.getpid()
    guardian = ModuleType("softqp_runtime_custody")
    now = time.monotonic_ns()
    slot_ns = LIMITS["generate"] * 10**9
    active = None if args.campaign else (custody, args.expected_request_sha256, policy, now + slot_ns)
    campaign_deadline = None

    def verify_source(source_file, profile_sha256):
        require(not violations, "source loader contract invalidated this worker")
        require_owned_job()
        require(live and os.getpid() == pid and sys.modules.get(guardian.__name__) is guardian,
                "active worker custody differs")
        require(profile_sha256 is None or profile_sha256 == args.expected_profile_sha256, "active profile digest differs")
        _, relative, _ = held.identify(source_file)
        require(relative == "data-pipeline/pipeline/learned_comparison/generator.py",
                "registered dispatcher source differs")

    def verify_active_worker(handle, *, operation, request_sha256, source_file, profile_sha256=None):
        verify_source(source_file, profile_sha256)
        require(active is not None and active[0] is handle and operation == "generate-source" and
                request_sha256 == active[1], "active source slot custody differs")
        require(time.monotonic_ns() < active[3], "active source slot deadline exceeded")

    def read_active_policy(handle, **scope):
        verify_active_worker(handle, **scope)
        return active[2]

    def read_active_campaign_policy(handle, *, request_sha256, source_file, profile_sha256=None):
        verify_source(source_file, profile_sha256)
        require(args.campaign and handle is custody and request_sha256 == args.expected_request_sha256,
                "active campaign custody differs")
        require(campaign_deadline and time.monotonic_ns() < campaign_deadline, "active campaign deadline exceeded")
        return policy

    if args.campaign:
        next_slot, end, seconds, entries = campaign_bounds(args, (raw, policy))
        campaign_deadline = now + seconds * 10**9

        @contextmanager
        def activate_generator_slot(handle, *, request_sha256, source_file, slot_request, slot_policy, ordinal):
            nonlocal active, next_slot
            read_active_campaign_policy(handle, request_sha256=request_sha256, source_file=source_file)
            require(active is None and type(ordinal) is int and ordinal == next_slot < end,
                    "source slot is concurrent, absent or out of order")
            require(type(slot_request) is bytes and type(slot_policy) is bytes and
                    len(slot_request) <= 65536 and len(slot_policy) <= 65536, "unbounded slot inputs")
            request_digest = sha256(slot_request).hexdigest()
            entry = entries[ordinal]
            require(request_digest == entry["request_sha256"] and sha256(slot_policy).hexdigest() ==
                    entry["policy_sha256"], "active slot identity differs from approved plan")
            name = f"slot-{ordinal:05d}"
            write_marker(args.run, name + "-start.json", {"ordinal": ordinal, "pid": pid,
                         "request_sha256": request_digest})
            ack = args.run / (name + "-ack.json")
            started = time.monotonic()
            while not ack.is_file():
                require(time.monotonic() - started < 10, "supervisor slot ACK deadline")
                time.sleep(.02)
            observed_ack = read_marker(ack)
            deadline = observed_ack.get("deadline_monotonic_ns")
            require(observed_ack == {"ordinal": ordinal, "request_sha256": request_digest,
                                     "deadline_monotonic_ns": deadline} and type(deadline) is int and
                    time.monotonic_ns() < deadline <= time.monotonic_ns() + slot_ns,
                    "supervisor slot ACK or deadline differs")
            started = time.monotonic()
            child = object()
            active = (child, request_digest, slot_policy, deadline)
            try:
                yield child
            finally:
                active = None
                duration = time.monotonic() - started
                require(duration < LIMITS["generate"] and time.monotonic_ns() < deadline,
                        "actual source slot deadline exceeded")
                write_marker(args.run, name + "-done.json", {"ordinal": ordinal, "pid": pid,
                             "request_sha256": request_digest, "worker_seconds": duration})
                next_slot += 1

        guardian.read_active_campaign_policy = read_active_campaign_policy
        guardian.activate_generator_slot = activate_generator_slot
    guardian.verify_active_worker = verify_active_worker
    guardian.read_active_policy = read_active_policy
    require(guardian.__name__ not in sys.modules, "unexpected preexisting active custody module")
    sys.modules[guardian.__name__] = guardian
    try:
        if args.campaign:
            result = generator.dispatch_registered_campaign(raw, custody)
            require(next_slot == end, "registered campaign returned with an incomplete approved projection")
        else:
            result = generator.dispatch_registered_request(raw, custody)
        require(type(result) is dict and len(json.dumps(result, allow_nan=False).encode()) <= 2**20,
                "registered dispatcher returned nondeclarative or excessive observation")
        return result
    finally:
        live = False
        active = None
        sys.modules.pop(guardian.__name__, None)


class CheckedImports:
    """Refuse non-inventory origins before an ordinary import executes."""
    def __init__(self, custody):
        self.custody = custody

    def find_distributions(self, context):
        return PathFinder.find_distributions(context)

    def find_spec(self, fullname, path=None, target=None):
        found = PathFinder.find_spec(fullname, path, target)
        if found is not None and found.origin is not None:
            self.custody.identify(found.origin)
        return found


def constrain_source_loader(profile, roots, held, scratch):
    """Check explicit file loaders before a generated module can execute."""
    import re
    original = SourceFileLoader.get_code
    derived = profile["scientific_runtime"].get("derived_python", {})
    require(set(derived) <= {"torch_geometric.nn.conv.le_conv_LEConv_propagate"},
            "unapproved derived source module roster")
    violations = []
    for recipe in derived.values():
        for relative, fingerprint in recipe["recipe"].items():
            kind, _, identity = held.identify(roots["runtime"] / relative)
            require(kind == "runtime" and identity[1] == fingerprint, "derived source recipe differs")

    def checked(loader, fullname):
        try:
            path = Path(loader.path)
            try:
                kind, _, _ = held.identify(path)
            except ValueError:
                # Only an externally pinned source recipe may write executable
                # source into fresh job scratch. Cached bytes have no authority.
                recipe = derived.get(fullname)
                require(recipe is not None and path.resolve(strict=True).parts == path.parts and
                        path.parent == scratch and re.fullmatch(re.escape(fullname) + r"_[a-z0-9_]{8}\.py", path.name),
                        f"unadmitted explicit source loader: {fullname}")
                held.check(scratch, "derived-runtime", {path.name: recipe["identity"]},
                           selected=True, hold_directories=False)
                kind, _, _ = held.identify(path)
            if kind == "derived-runtime":
                require(fullname in derived and path.name.startswith(fullname + "_"),
                        "substituted derived-source module name")
            return original(loader, fullname)
        except (ValueError, OSError) as error:
            # PyG otherwise catches template-load errors and falls back.
            violations.append(str(error))
            raise

    SourceFileLoader.get_code = checked
    return violations


def stage_file(root, stage, observed, started, *, limit=None):
    limit = LIMITS[stage] if limit is None else limit
    seconds = time.monotonic() - started
    require(seconds < limit, f"{stage} actual worker deadline exceeded")
    result = {"stage": stage, "pid": os.getpid(), "observed": observed, "worker_seconds": seconds}
    temporary = root / (stage + ".pending")
    temporary.write_text(json.dumps(result, allow_nan=False, sort_keys=True), encoding="utf-8")
    temporary.rename(root / (stage + ".json"))


def require_owned_job(locator=None):
    """The environment names a kernel object. Only live membership grants entry."""
    name = locator or os.environ.get("SOFTQP_SCIENTIFIC_JOB")
    require(name and name.startswith("SoftQP-Lesson-"), "worker has no owned Windows job")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenJobObjectW.restype = wintypes.HANDLE
    api.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    job = api.OpenJobObjectW(4, False, name)  # JOB_OBJECT_QUERY
    require(job, "worker cannot resolve its live Windows job")
    try:
        contained = wintypes.BOOL()
        require(api.IsProcessInJob(api.GetCurrentProcess(), job, ctypes.byref(contained))
                and contained.value, "worker is outside the nominated Windows job")
    finally:
        api.CloseHandle(job)


def extension_points_disabled():
    """Block legacy third-party extension points in this worker only."""
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.SetProcessMitigationPolicy.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
    api.GetProcessMitigationPolicy.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
    # ProcessExtensionPointDisablePolicy from the Windows SDK.
    requested, observed = wintypes.DWORD(1), wintypes.DWORD()
    require(api.SetProcessMitigationPolicy(6, ctypes.byref(requested), ctypes.sizeof(requested))
            and api.GetProcessMitigationPolicy(api.GetCurrentProcess(), 6, ctypes.byref(observed),
                                              ctypes.sizeof(observed)) and observed.value & 1,
            "cannot establish process-local legacy extension mitigation")
    return True


def host_scope(args, stamp):
    approved = stamp["host_native"]
    require(set(approved) == {"file", "identity", "signature_receipt_sha256"}, "invalid host-native scope")
    path = Path(approved["file"])
    require(path.is_absolute() and path.resolve(strict=True).parts == path.parts and path.name.casefold() == "mpoav.dll",
            "substituted host-native path")
    receipt = json.loads(load(args.profile / "host-native-receipt.json", approved["signature_receipt_sha256"]))
    require(receipt["status"] == "Valid" and receipt["path"] == str(path) and
            receipt["sha256"] == approved["identity"][1] and
            receipt["publisher"].startswith("CN=Microsoft Windows, O=Microsoft Corporation,"),
            "unapproved host-native signature")
    return path.parent, {path.name: approved["identity"]}


def loaded_native(custody, roots):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = wintypes.HANDLE
    proc = api.GetCurrentProcess()
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.DWORD)]
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE,
                                          wintypes.LPWSTR, wintypes.DWORD]
    handles = (wintypes.HMODULE * 2048)()
    needed = wintypes.DWORD()
    require(psapi.EnumProcessModules(proc, handles, ctypes.sizeof(handles), ctypes.byref(needed)),
            "cannot enumerate loaded Windows binaries")
    require(needed.value <= ctypes.sizeof(handles), "loaded Windows binary inventory truncated")
    output = []
    windows = Path(os.environ["SystemRoot"]).resolve(strict=True)
    for handle in handles[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
        name = ctypes.create_unicode_buffer(32768)
        require(0 < psapi.GetModuleFileNameExW(proc, handle, name, len(name)) < len(name),
                "unavailable loaded Windows binary path")
        path = Path(name.value).resolve(strict=True)
        for kind, root in roots.items():
            if path.is_relative_to(root):
                actual_kind, relative, identity = custody.identify(path)
                require(kind == actual_kind, "native binary root differs")
                output.append(dict(root=kind, path=relative, sha256=identity[1]))
                break
        else:
            require(any(path.is_relative_to(windows / child) for child in ("System32", "WinSxS")),
                    f"external native binary: {path}")
            # The Windows system binaries remain the host trust boundary.
            from hashlib import file_digest
            with path.open("rb") as handle:
                os_sha = file_digest(handle, "sha256").hexdigest()
            output.append(dict(root="windows", path=path.relative_to(windows).as_posix(), sha256=os_sha))
    return sorted(output, key=lambda row: (row["root"], row["path"]))


def import_runtime(profile, manifest, roots, held, *, fixtures, product=True):
    runtime, base, source = (roots[key] for key in ("runtime", "base", "source"))
    site = runtime / "Lib" / "site-packages"
    cmeel = site / "cmeel.prefix" / "lib" / "python3.12" / "site-packages"
    sys.prefix = sys.exec_prefix = str(runtime)
    sys.path[:] = [str(base / "DLLs"), str(base / "Lib"), str(base), str(site), str(cmeel),
                   str(source / "data-pipeline")]
    guard = CheckedImports(held)
    position = sys.meta_path.index(PathFinder)
    sys.meta_path[position] = guard
    modules = {}
    for name, expected in profile["imported_origins"].items():
        module = importlib.import_module(name)
        kind, rel, identity = held.identify(module.__spec__.origin)
        require(kind == "runtime" and rel == expected["relative_path"] and identity[1] == expected["sha256"]
                and rel in manifest["module_owners"], f"actual mapped package origin differs: {name}")
        modules[name] = {"distribution": manifest["module_owners"][rel], "path": rel, "sha256": identity[1]}
    pipeline_sources = sorted(rel for rel in manifest["source"]
                              if rel.startswith("data-pipeline/pipeline/") and rel.endswith(".py"))
    for expected in pipeline_sources if product else ():
        name = expected.removeprefix("data-pipeline/").removesuffix(".py").removesuffix("/__init__")
        name = name.replace("/", ".")
        module = importlib.import_module(name)
        kind, relative, identity = held.identify(module.__spec__.origin)
        require(kind == "source" and relative == expected, "product origin differs")
        modules[name] = {"path": relative, "sha256": identity[1]}
    import torch
    import threadpoolctl
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    limiter = threadpoolctl.threadpool_limits(1)
    require(torch.version.cuda is None and torch.get_num_threads() == torch.get_num_interop_threads() == 1,
            "CPU thread or CUDA admission failed")
    require(all(row["num_threads"] == 1 for row in threadpoolctl.threadpool_info()), "native thread limit")
    # Append only the separately checked test-tool path, after all runtime packages.
    if fixtures:
        sys.path.extend((str(roots["tools"]), str(source / "tests")))
    return modules, limiter


def learning_component(args, stamp):
    return source_code(args.profile / "learning_runtime.py", stamp["learning_runtime_sha256"])


def wait_marker(path, maximum=10):
    deadline = time.monotonic() + maximum
    while not path.is_file():
        require(time.monotonic() < deadline, f"owned marker deadline: {path.name}")
        time.sleep(.02)
    return path



def check_learning_parent(owner):
    class ProcessEntry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD),
                    ("image", wintypes.WCHAR * 260)]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    api.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    api.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = api.CreateToolhelp32Snapshot(2, 0)
    require(snapshot != ctypes.c_void_p(-1).value, "cannot observe learning parent ancestry")
    processes = {}
    try:
        item = ProcessEntry()
        item.size = ctypes.sizeof(item)
        observed = api.Process32FirstW(snapshot, ctypes.byref(item))
        while observed:
            processes[item.pid] = (item.parent, item.image.casefold())
            observed = api.Process32NextW(snapshot, ctypes.byref(item))
    finally:
        api.CloseHandle(snapshot)
    child_parent, _ = processes.get(os.getpid(), (None, None))
    launcher_parent, launcher_image = processes.get(child_parent, (None, None))
    require(owner in processes and (child_parent == owner or
            (launcher_image == "python.exe" and launcher_parent == owner)), "learning owner process ancestry differs")

def leaf_launch(args, stamp):
    require(args.learning_child and args.worker and not args.learning and not args.campaign and
            stamp["source_kind"] == "committed-product-checkout"
            and args.run.name == "worker" and args.tools is None and args.owning_job,
            "leaf launch outside committed fixed learning scope")
    helper = learning_component(args, stamp)
    path = wait_marker(args.run / "learning-launch.json")
    require(path.stat().st_size <= 8192, "unbounded learning leaf descriptor")
    raw = load(path, args.expected_learning_launch_sha256)
    spec = helper["canonical"](raw)
    require(set(spec) == {"schema", "nonce", "operation", "method", "seed", "profile_sha256",
                         "request_sha256", "policy_sha256", "deadline_monotonic_ns", "owner", "boot_sha256"}
            and spec["schema"] == "softqp.r4.learning-leaf/1"
            and spec["operation"] in helper["OPERATIONS"] and spec["method"] in helper["METHODS"]
            and spec["seed"] in (41001, 41002, 41003)
            and spec["profile_sha256"] == args.expected_profile_sha256
            and all(helper["hex_digest"](spec[key]) for key in ("request_sha256", "policy_sha256", "boot_sha256"))
            and type(spec["nonce"]) is str and len(spec["nonce"]) == 32
            and all(ch in "0123456789abcdef" for ch in spec["nonce"])
            and type(spec["owner"]) is int and spec["owner"] > 0
            and type(spec["deadline_monotonic_ns"]) is int and
            time.monotonic_ns() < spec["deadline_monotonic_ns"] <= time.monotonic_ns() + LEARNING_LIMIT * 10**9,
            "learning leaf descriptor differs")
    check_learning_parent(spec["owner"])
    return helper, spec


def create_learning_child(args, helper, root, payload):
    # Nested Windows jobs preserve teardown at both ownership levels. The
    # inherited outer job is checked by the actual Python image before admission.
    from pipeline.learned_comparison.native_labels import _OwnedWorker
    locator = os.environ["SOFTQP_SCIENTIFIC_JOB"]
    data = helper["encode"](payload)
    command = [
        str(args.python), "-I", "-S", "-B", "-u", "-X", "pycache_prefix=" + str(root / "empty-bytecode-prefix"),
        str(Path(__file__).resolve()), "--worker", "--learning-child", "--owning-job", locator,
        "--python", str(args.python), "--base-python", str(args.base_python), "--profile", str(args.profile),
        "--source", str(args.source), "--run", str(root), "--expected-profile-sha256", args.expected_profile_sha256,
        "--expected-learning-launch-sha256", helper["digest"](data),
    ]
    child = _OwnedWorker(root, command, args.python, nonce=payload["nonce"])
    try:
        with (root / "learning-launch.pending").open("xb") as handle:
            handle.write(data)
        (root / "learning-launch.pending").rename(root / "learning-launch.json")
    except BaseException:
        child.close()
        raise
    return child


def learning_installed(args, helper, spec, observation, started):
    seconds = time.monotonic() - started
    require(seconds < LIMITS["scan"], "learning leaf installed-file deadline")
    audit = dict(full_files=True, read_only=True, distributions=49,
                 full_source_files_checked=observation["wheel_source_files"],
                 profile_sha256=args.expected_profile_sha256)
    installed = dict(nonce=spec["nonce"], pid=os.getpid(), audit=audit, seconds=seconds)
    content = helper["encode"](installed)
    with (args.run / "installed.pending").open("xb") as handle:
        handle.write(content)
    (args.run / "installed.pending").rename(args.run / "installed.json")
    ack = wait_marker(args.run / "import-ack.json")
    require(read_marker(ack) == {"installed_sha256": helper["digest"](content)}, "learning leaf import ACK differs")
    return audit, installed


def hold_learning_boot(args, held, helper, spec):
    path = wait_marker(args.run / "boot.json")
    # The task can contain the fixed per-head inventory, but no input paths.
    require(path.stat().st_size <= 2**24, "learning leaf boot exceeds bounded task size")
    raw = load(path, spec["boot_sha256"])
    boot = helper["canonical"](raw)
    task = boot["task"]
    operation = "train" if spec["operation"] == "train-model" else "calibrate"
    expected = {key: spec[key] for key in ("operation", "request_sha256", "policy_sha256", "profile_sha256")}
    require(set(boot) == {"nonce", "task", "authority"} and boot["authority"] == expected
            and boot["nonce"] == spec["nonce"] and task["operation"] == operation
            and task["method"] == spec["method"] and task["seed"] == spec["seed"]
            and helper["hex_digest"](task["permit_scope"]), "learning boot scope differs from fixed descriptor")
    held.check(args.run, "learning-boot", {path.name: [len(raw), spec["boot_sha256"]]},
               selected=True, hold_directories=False)


def require_learning_leaf(args, held, roots, spec, violations):
    require_owned_job(args.owning_job)
    require(not violations and time.monotonic_ns() < spec["deadline_monotonic_ns"],
            "learning leaf source/deadline custody invalidated")
    module = sys.modules.get("pipeline.learned_comparison.training_worker")
    require(module is not None, "fixed learning worker source is absent")
    kind, relative, _ = held.identify(module.__spec__.origin)
    require(kind == "source" and relative == "data-pipeline/pipeline/learned_comparison/training_worker.py",
            "fixed learning leaf source differs")
    loaded_native(held, roots)


def worker(args):
    started = time.monotonic()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and
            sys.flags.optimize == 0 and sys.pycache_prefix == str(args.run / "empty-bytecode-prefix") and
            not Path(sys.pycache_prefix).exists(), "isolated no-site and unused bytecode prefix required")
    require_owned_job(args.owning_job if args.learning_child else None)
    extension_points_disabled()
    profile, stamp, manifest = configuration(args)
    launch = launch_inputs(args, stamp)
    require(not args.learning_child or launch is None, "learning leaf accepts only its owned launch descriptor")
    leaf = leaf_launch(args, stamp) if args.learning_child else None
    fixtures = launch is None and leaf is None
    roots = dict(runtime=Path(sys.executable).parents[1].resolve(strict=True),
                 base=Path(sys.base_prefix).resolve(strict=True), source=args.source)
    if fixtures:
        require(args.tools is not None, "excluded controls need the admitted test-only bridge")
        roots["tools"] = args.tools
    require(Path(sys._base_executable).resolve() == roots["base"] / "python.exe", "unexpected active base executable")
    custody = source_code(args.profile / "custody.py", stamp["custody_module_sha256"])
    host_root, host_manifest = host_scope(args, stamp)
    with custody["HeldInventory"]() as held:
        for kind, root in roots.items():
            held.check(root, kind, manifest[kind], selected=(kind == "source" and not fixtures))
        held.check(host_root, "host-native", host_manifest, selected=True)
        sys.prefix = sys.exec_prefix = str(roots["runtime"])
        sys.path.append(str(roots["runtime"] / "Lib" / "site-packages"))
        checker = source_code(args.profile / "check_lock.py", stamp["engine_checker_sha256"])
        # The held complete byte inventory checks every source file. The engine's
        # metadata gate authenticates its wheel-record plan, notices and defaults.
        lock = checker["check"](args.profile, args.expected_profile_sha256, full=False)
        expected_source_count = sum(row["source_file_count"] for row in profile["distributions"])
        require(lock["distributions"] == len(profile["distributions"]) == 49, "wrong distribution count")
        # Independently verify each wheel RECORD byte identity as well, without reopening data.
        import base64
        from importlib import metadata
        actual_source_count = 0
        for dist in metadata.distributions():
            for rel, recorded, size in checker["source_manifest"](dist, roots["runtime"]):
                actual_size, hex_digest = manifest["runtime"][rel]
                require(recorded == "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(hex_digest)).decode().rstrip("=")
                        and actual_size == size, f"wheel RECORD differs from held bytes: {rel}")
                actual_source_count += 1
        require(actual_source_count == expected_source_count, "incomplete RECORD byte verification")
        held.recheck_names()
        scan = dict(distributions=49, wheel_source_files=expected_source_count,
                    inventory={kind: len(manifest[kind]) for kind in roots}, handles_held=True,
                    executable=str(Path(sys.executable).resolve()), base_executable=str(Path(sys._base_executable).resolve()))
        if leaf is None:
            stage_file(args.run, "scan", scan, started)
        else:
            audit, installed = learning_installed(args, *leaf, scan, started)
        started = time.monotonic()
        if stamp.get("derived_python"):
            independent = json.loads(load(args.profile / "derived-recipe-receipt.json",
                                          stamp["derived_receipt_sha256"]))
            row, = independent["observed"]
            declared = stamp["derived_python"][row["module"]]
            require(declared["identity"] == [row["bytes"], row["sha256"]] and
                    declared["recipe"]["Lib/site-packages/torch_geometric/nn/conv/propagate.jinja"] ==
                    row["template_sha256"], "independent derived-source receipt differs")
        violations = constrain_source_loader(profile, roots, held, args.run)
        imported, limiter = import_runtime(profile, manifest, roots, held, fixtures=fixtures, product=leaf is None)
        roots["host-native"] = host_root
        controls = source_code(args.profile / "controls.py", stamp["controls_sha256"])
        # The test-only fixture tooling stays outside registered execution.
        if fixtures:
            controls["warm_imports"]()
        defaults = controls["live_defaults"](args.profile, stamp)
        if leaf is not None:
            helper, spec = leaf
            hold_learning_boot(args, held, helper, spec)
            from pipeline.learned_comparison import training_worker
        stage_file(args.run, "imports", dict(modules=imported, defaults_sha256=defaults,
                    native=loaded_native(held, roots), isolated=True, site_hooks_run=False,
                    legacy_extension_points_disabled=True), started)
        imports_seconds = time.monotonic() - started
        started = time.monotonic()
        if leaf is not None:
            live = lambda: require_learning_leaf(args, held, roots, spec, violations)
            live()
            training_worker.main_verified(args.run, spec["nonce"], require_live=live, audit=audit,
                                          installed=installed, import_seconds=imports_seconds)
        elif args.learning:
            helper = learning_component(args, stamp)
            def live():
                require_owned_job()
                require(not violations, "source loader contract invalidated learning custody")
            result = helper["dispatch_learning"](
                args, held, launch, verify_live=live,
                create_child=lambda root, payload: create_learning_child(args, helper, root, payload),
            )
            stage_file(args.run, "learn", result, started, limit=LEARNING_LIMIT)
        elif fixtures:
            problem, evidence, observation = controls["reference"]()
            stage_file(args.run, "reference", observation, started)
            for stage, operation in (
                ("cold", lambda: controls["cold"](problem, evidence)),
                ("gradient", controls["gradient"]), ("reader", lambda: controls["reader"](args.run))
            ):
                started = time.monotonic()
                stage_file(args.run, stage, operation(), started)
        else:
            limit = campaign_bounds(args, launch)[2] if args.campaign else LIMITS["generate"]
            stage_file(args.run, "generate", dispatch_registered(args, stamp, held, *launch, violations), started, limit=limit)
        started = time.monotonic()
        held.recheck_names()
        origins = {}
        for name, module in tuple(sys.modules.items()):
            origin = getattr(getattr(module, "__spec__", None), "origin", None)
            if origin and origin not in ("built-in", "frozen"):
                kind, relative, identity = held.identify(origin)
                origins[name] = {"root": kind, "path": relative, "sha256": identity[1]}
        require(not violations, f"explicit source loader refusal: {violations[:4]}")
        stage_file(args.run, "final", dict(modules=origins, native=loaded_native(held, roots)), started)


def supervise(args):
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
            and not sys.flags.optimize, "isolated no-site supervisor required")
    _, stamp, manifest = configuration(args)
    launch = launch_inputs(args, stamp)
    require(not (args.learning and args.campaign) and not args.learning_child and not args.owning_job,
            "mutually exclusive fixed launch modes")
    if args.learning:
        request, policy, _ = learning_component(args, stamp)["learning_scope"](launch, args.expected_profile_sha256)
        require(Path(policy["admission"]["product_root"]).resolve(strict=True).parts == args.source.parts,
                "learning authority product root differs from committed worker source")
    campaign = campaign_bounds(args, launch) if args.campaign else None
    protected = (args.source, args.profile, args.python.parents[1], args.base_python.parent, args.tools)
    require(not any(args.run.is_relative_to(root) for root in protected if root is not None),
            "qualification scratch is inside a protected input root")
    require(shutil.disk_usage(args.run.parent).free >= 20 * 2**30, "external free disk below 20 GiB")
    args.run.mkdir()
    # Use the actual existing product job implementation, pinned in the selected snapshot.
    launcher = "data-pipeline/pipeline/lesson_process.py"
    resources = "data-pipeline/pipeline/coupled_resources.py"
    job_type = source_code(args.source / launcher, manifest["source"][launcher][1])["WindowsJob"]
    sample = source_code(args.source / resources, manifest["source"][resources][1])["process_memory"]
    for path, digest in ((args.python, stamp["python_sha256"]), (args.base_python, stamp["base_python_sha256"]),
                         (args.base_python.with_name("python312.dll"), stamp["python_dll_sha256"])):
        load(path, digest)
    job = job_type()
    custody = source_code(args.profile / "custody.py", stamp["custody_module_sha256"])
    bootstrap = custody["HeldInventory"]()
    process = None
    result = {"format": "softqp.product-runtime-observation/v1", "i1_issued": False,
              "profile_sha256": args.expected_profile_sha256, "source_head": stamp["source_head"],
              "source_manifest_sha256": stamp["source_manifest_sha256"], "stages": {}, "owned_pids": []}
    start = time.monotonic()
    try:
        bootstrap.check(args.base_python.parent, "base", manifest["base"])
        host_root, host_manifest = host_scope(args, stamp)
        bootstrap.check(host_root, "host-native", host_manifest, selected=True)
        from shutil import which
        windows = Path(os.environ["SystemRoot"]).resolve(strict=True)
        git = Path(which("git") or "").resolve(strict=True).parent
        env = dict(SystemRoot=str(windows), WINDIR=str(windows), TEMP=str(args.run), TMP=str(args.run),
                   PATH=os.pathsep.join(map(str, (windows/"System32", windows, git))), CUDA_VISIBLE_DEVICES="",
                   SOFTQP_SCIENTIFIC_JOB=job.name)
        env.update({key: "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                                         "NUMEXPR_NUM_THREADS", "RAYON_NUM_THREADS")})
        command = [str(args.python), "-I", "-S", "-B", "-u", "-X",
                   "pycache_prefix=" + str(args.run / "empty-bytecode-prefix"), str(Path(__file__).resolve()),
                   "--worker", *sys.argv[1:]]
        result["command"] = command
        with (args.run / "stdout.log").open("xb") as stdout, (args.run / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(command, cwd=args.run, env=env, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, creationflags=4)
            job.attach_and_resume(process)
            phases = ("scan", "imports", "reference", "cold", "gradient", "reader", "final") if launch is None else (
                "scan", "imports", "learn" if args.learning else "generate", "final")
            for stage in phases:
                limit = LEARNING_LIMIT if stage == "learn" else (campaign[2] if stage == "generate" and campaign else LIMITS[stage])
                slot, finish, _, entries = campaign if stage == "generate" and campaign else (0, 0, 0, ())
                slot_started = None
                phase_start = time.monotonic()
                peak = 0
                path = args.run / (stage + ".json")
                while True:
                    class Members(ctypes.Structure):
                        _fields_ = [("assigned", wintypes.DWORD), ("count", wintypes.DWORD),
                                    ("ids", ctypes.c_size_t * 16)]
                    members = Members()
                    require(job.api.QueryInformationJobObject(job.handle, 3, ctypes.byref(members),
                            ctypes.sizeof(members), None), "cannot query owned process tree")
                    require(members.assigned == members.count <= 16, "incomplete owned process inventory")
                    result["owned_pids"] = sorted(set(result["owned_pids"]) | set(members.ids[:members.count]))
                    total = 0
                    for pid in members.ids[:members.count]:
                        try:
                            total += sample(pid)[1]
                        except OSError:
                            if process.poll() is None:
                                raise
                    peak = max(peak, total)
                    elapsed = time.monotonic() - phase_start
                    require(elapsed < limit and peak < RSS, f"{stage} deadline or RSS bound exceeded")
                    require((args.run / "stderr.log").stat().st_size < 2**22, "diagnostic limit exceeded")
                    if slot < finish:
                        name = f"slot-{slot:05d}"
                        ready, done = (args.run / (name + suffix) for suffix in ("-start.json", "-done.json"))
                        expected_request = entries[slot]["request_sha256"]
                        if slot_started is None and ready.is_file():
                            marker = read_marker(ready)
                            require(marker["ordinal"] == slot and marker["pid"] in result["owned_pids"] and
                                    marker["request_sha256"] == expected_request, "unexpected active slot marker")
                            slot_started = time.monotonic()
                            write_marker(args.run, name + "-ack.json",
                                         {"ordinal": slot, "request_sha256": expected_request,
                                          "deadline_monotonic_ns": time.monotonic_ns() + LIMITS["generate"] * 10**9})
                        if slot_started is not None:
                            require(time.monotonic() - slot_started < LIMITS["generate"], "source slot deadline exceeded")
                            if done.is_file():
                                ended = read_marker(done)
                                require(ended["ordinal"] == slot and ended["pid"] in result["owned_pids"] and
                                        ended["request_sha256"] == expected_request and
                                        0 <= ended["worker_seconds"] < LIMITS["generate"],
                                        "source slot terminal marker differs")
                                slot += 1
                                slot_started = None
                    if path.is_file() and slot == finish:
                        entry = json.loads(path.read_bytes())
                        require(entry["stage"] == stage and entry["pid"] in result["owned_pids"],
                                "worker observation path does not bind the owned phase")
                        result["stages"][stage] = dict(seconds=elapsed, peak_tree_working_set_bytes=peak,
                            deadline_seconds=limit, **entry)
                        break
                    require(process.poll() is None, f"owned process exited before {stage}")
                    time.sleep(.05)
            require(process.wait(timeout=3) == 0, "worker shutdown failed")
        result["status"] = "software-qualification-pass" if launch is None else "registered-dispatch-observed"
    except BaseException as error:
        result.update(status="refused", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        try:
            job.close()
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)
            result["cleanup"] = "owned-process-tree-closed"
        finally:
            bootstrap.stack.close()
            result["total_seconds"] = time.monotonic() - start
            (args.run / "receipt.json").write_text(json.dumps(result, sort_keys=True, indent=2),
                                                   encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "total_seconds", "profile_sha256")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--campaign", action="store_true")
    parser.add_argument("--learning", action="store_true")
    parser.add_argument("--learning-child", action="store_true")
    parser.add_argument("--owning-job")
    parser.add_argument("--expected-learning-launch-sha256")
    parser.add_argument("--tools", type=lambda value: Path(value).resolve())
    for name in ("python", "base-python", "profile", "source", "run"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--expected-profile-sha256", required=True)
    for name in ("request", "policy"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve())
        parser.add_argument("--expected-" + name + "-sha256")
    arguments = parser.parse_args()
    (worker if arguments.worker else supervise)(arguments)
