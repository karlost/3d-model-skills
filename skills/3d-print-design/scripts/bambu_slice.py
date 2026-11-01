"""Safe Bambu Studio slicing from the command line (Windows).

Usage:
    python bambu_slice.py project.3mf                  # all plates, output next to it in <project>_slice/
    python bambu_slice.py project.3mf --plate 2 --out folder
    options: --timeout 600 (s), --mem-gb 8 (process memory limit)

Bambu Studio 2.08 shares one new-handler between the CLI and the GUI: when an allocation fails it shows
"Bambu Studio - Out of Memory" on top of all windows and then crashes on purpose (bash reports
Segmentation fault). So the script runs the CLI on its own hidden Windows desktop, where the dialog
bothers nobody, spots it by its title and kills the process. Other safeguards: a Job Object with a memory
limit that also kills the process if the script dies, a timeout, killing a process that hangs after
writing result.json (it happens), and a lock so that several sessions never slice at the same time.
--slice only: --export-3mf hangs on the hidden desktop until the timeout.

The dialog was mostly triggered by a short inherits_group list in multi-filament 3MFs from an old
bambu3mf.py (fixed 2026-10-17). The script reports such files as oom.

Output: time and grams per plate from result.json. Exit code 0 = OK, 1 = slicing error
(result.json), 2 = out of memory, 3 = timeout or crash without a result.
Set BAMBU_STUDIO_EXE if Bambu Studio is not in the default location.
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

if sys.platform != "win32":
    sys.exit("bambu_slice.py runs on Windows only. Elsewhere call the Bambu Studio CLI directly: "
             "bambu-studio --slice 0 --outputdir out project.3mf")

import ctypes.wintypes as w  # noqa: E402

EXE = os.environ.get("BAMBU_STUDIO_EXE", r"C:\Program Files\Bambu Studio\bambu-studio.exe")
OOM_TITLE = "Out of Memory"
LOCK_NAME = "Local\\claude-bambu-cli-slice"
EXIT_GRACE_S = 15

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR), ("lpTitle", w.LPWSTR),
                ("dwX", w.DWORD), ("dwY", w.DWORD), ("dwXSize", w.DWORD), ("dwYSize", w.DWORD),
                ("dwXCountChars", w.DWORD), ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
                ("dwFlags", w.DWORD), ("wShowWindow", w.WORD), ("cbReserved2", w.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", w.HANDLE), ("hStdOutput", w.HANDLE),
                ("hStdError", w.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", w.HANDLE), ("hThread", w.HANDLE), ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


JOB_EXT_INFO = 9
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
CREATE_SUSPENDED = 0x4
STARTF_USESTDHANDLES = 0x100
WAIT_TIMEOUT = 0x102
WNDENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

k32.CreateJobObjectW.restype = w.HANDLE
k32.CreateMutexW.restype = w.HANDLE
u32.CreateDesktopW.restype = w.HANDLE
u32.CreateDesktopW.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.c_void_p]
u32.EnumDesktopWindows.argtypes = [w.HANDLE, WNDENUMPROC, w.LPARAM]
k32.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
k32.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
k32.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
k32.CloseHandle.argtypes = [w.HANDLE]


def check(ok, what):
    if not ok:
        raise OSError(ctypes.get_last_error(), f"{what} failed: {ctypes.FormatError(ctypes.get_last_error())}")
    return ok


def window_titles(hdesk):
    titles = []

    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(hwnd, buf, 256)
        if buf.value:
            titles.append(buf.value)
        return True

    u32.EnumDesktopWindows(hdesk, WNDENUMPROC(cb), 0)
    return titles


def read_result(out):
    try:
        return json.loads((out / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(cli_args, out, timeout, mem_gb):
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").unlink(missing_ok=True)
    for g in out.glob("plate_*.gcode"):
        g.unlink()

    lock = check(k32.CreateMutexW(None, False, LOCK_NAME), "CreateMutex")
    t_wait = time.time()
    if k32.WaitForSingleObject(lock, timeout * 1000) == WAIT_TIMEOUT:
        return {"status": "timeout", "detail": "another slicing run holds the lock"}
    waited = time.time() - t_wait

    desk_name = f"claude-slice-{os.getpid()}"
    hdesk = check(u32.CreateDesktopW(desk_name, None, None, 0, 0x10000000, None), "CreateDesktop")
    job = check(k32.CreateJobObjectW(None, None), "CreateJobObject")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = int(mem_gb * 2**30)
    check(k32.SetInformationJobObject(w.HANDLE(job), JOB_EXT_INFO, ctypes.byref(info), ctypes.sizeof(info)),
          "SetInformationJobObject")

    log = open(out / "cli_log.txt", "wb")
    import msvcrt
    hlog = msvcrt.get_osfhandle(log.fileno())
    os.set_handle_inheritable(hlog, True)
    si = STARTUPINFOW(cb=ctypes.sizeof(STARTUPINFOW), lpDesktop=desk_name, dwFlags=STARTF_USESTDHANDLES,
                      hStdOutput=hlog, hStdError=hlog)
    pi = PROCESS_INFORMATION()
    cmd = subprocess.list2cmdline([EXE, *map(str, cli_args)])
    check(k32.CreateProcessW(EXE, ctypes.create_unicode_buffer(cmd), None, None, True, CREATE_SUSPENDED,
                             None, str(out), ctypes.byref(si), ctypes.byref(pi)), "CreateProcess")
    check(k32.AssignProcessToJobObject(w.HANDLE(job), pi.hProcess), "AssignProcessToJobObject")
    k32.ResumeThread(pi.hThread)

    t0, status, done_at = time.time(), None, None
    while True:
        if k32.WaitForSingleObject(pi.hProcess, 500) != WAIT_TIMEOUT:
            break
        if any(OOM_TITLE in t for t in window_titles(hdesk)):
            status = "oom"
        elif time.time() - t0 > timeout:
            status = "timeout"
        elif read_result(out) is not None:
            done_at = done_at or time.time()
            if time.time() - done_at > EXIT_GRACE_S:
                status = "hung-after-result"
        if status:
            k32.TerminateProcess(pi.hProcess, 1)
            k32.WaitForSingleObject(pi.hProcess, 5000)
            break
    code = w.DWORD()
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    k32.QueryInformationJobObject(w.HANDLE(job), JOB_EXT_INFO, ctypes.byref(info), ctypes.sizeof(info), None)
    for h in (pi.hThread, pi.hProcess, job):
        k32.CloseHandle(h)
    u32.CloseDesktop(w.HANDLE(hdesk))
    log.close()
    k32.ReleaseMutex(lock)
    k32.CloseHandle(lock)

    res = read_result(out)
    if status is None:
        exit_code = ctypes.c_int32(code.value).value
        if res is not None and res.get("return_code") == 0:
            status = "ok"
        elif res is not None:
            status = "error"
        else:
            status = "crash"
    else:
        exit_code = None
    return {"status": status, "exit_code": exit_code, "seconds": round(time.time() - t0, 1),
            "waited_for_lock": round(waited, 1), "peak_gb": round(info.PeakProcessMemoryUsed / 2**30, 2),
            "result": res}


def main():
    # A Git Bash console is cp1252 and non-ASCII output would crash only after result.json was written
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--plate", type=int, default=0, help="0 = all plates")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--mem-gb", type=float, default=8)
    a = ap.parse_args()
    project = a.project.resolve()
    out = (a.out or project.with_name(project.stem + "_slice")).resolve()
    r = run(["--slice", a.plate, "--outputdir", out, project], out, a.timeout, a.mem_gb)

    res = r.pop("result")
    print(f"{project.name}: {r['status']}  ({r['seconds']} s, peak {r['peak_gb']} GB"
          + (f", waited for lock {r['waited_for_lock']} s" if r["waited_for_lock"] > 1 else "") + ")")
    if r["status"] == "oom":
        print(f"  Bambu Studio reported Out of Memory (limit {a.mem_gb} GB). The dialog was on the hidden desktop, process killed.")
    if r["status"] == "hung-after-result":
        print("  The process hung after writing the result and was killed. The result is valid.")
    if r["status"] == "crash":
        print(f"  Bambu Studio ended without result.json, code {r['exit_code']:#010x}.")
    if res:
        if res.get("return_code") != 0:
            print(f"  error {res.get('return_code')}: {res.get('error_string')}")
        for p in res.get("sliced_plates", []):
            grams = sum(f.get("total_used_g", 0) for f in p.get("filaments", []))
            warn = p.get("warning_message") or ""
            print(f"  plate {p['id']}: {p['total_predication'] / 60:.1f} min, {grams:.2f} g"
                  + (f"  warning: {warn}" if warn else ""))
        print(f"  output: {out}")
    ok = r["status"] in ("ok", "hung-after-result") and res and res.get("return_code") == 0
    sys.exit(0 if ok else {"error": 1, "oom": 2}.get(r["status"], 1 if res else 3))


if __name__ == "__main__":
    main()
