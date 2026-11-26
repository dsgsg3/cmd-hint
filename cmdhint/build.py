import atexit
import ctypes
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes as wt

import make_version_info
import winapi
from version import VERSION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")
NAME = "命令提示.exe"
EXE = os.path.join(DIST, NAME)
PREV = os.path.join(DIST, "命令提示.上一版.exe")
LOG_NAME = "命令提示-打包失败.log"
BAR_TIMEOUT = 25


class Entry(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", wt.WCHAR * 260)]


def say(text):
    print(text, flush=True)


def fail(text):
    say("")
    say(text)
    sys.exit(1)


def running_pids():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(Entry)]
    k32.CloseHandle.argtypes = [wt.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    pids, e = [], Entry()
    e.dwSize = ctypes.sizeof(Entry)
    more = k32.Process32FirstW(snap, ctypes.byref(e))
    while more:
        if e.szExeFile.lower() == NAME:
            pids.append(e.th32ProcessID)
        more = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return pids


def stop_running():
    for _ in range(50):
        pids = running_pids()
        if not pids:
            return
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        time.sleep(0.2)
    fail("没能结束正在运行的程序。请在托盘图标上右键选「退出」，再重新运行。")


def replace(src, dst):
    tmp = dst + ".tmp"
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def file_version(path):
    ver = ctypes.WinDLL("version")
    size = ver.GetFileVersionInfoSizeW(path, None)
    if not size:
        return ""
    data = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(path, 0, size, data):
        return ""
    buf, n = ctypes.c_void_p(), wt.UINT()
    if not ver.VerQueryValueW(data, "\\", ctypes.byref(buf), ctypes.byref(n)) or n.value < 16:
        return ""
    ffi = ctypes.cast(buf, ctypes.POINTER(wt.DWORD))
    ms, ls = ffi[2], ffi[3]
    return "%d.%d.%d.%d" % (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def bar_visible(timeout):
    u = ctypes.WinDLL("user32", use_last_error=True)
    found = []

    def cb(hw, _):
        if u.IsWindowVisible(hw):
            cls = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(hw, cls, 64)
            if cls.value == "TkTopLevel":
                pid = wt.DWORD()
                u.GetWindowThreadProcessId(hw, ctypes.byref(pid))
                if winapi.process_name(pid.value) == NAME:
                    r = wt.RECT()
                    u.GetWindowRect(hw, ctypes.byref(r))
                    if r.right - r.left > 300:
                        found.append(hw)
        return True

    end = time.time() + timeout
    while time.time() < end:
        del found[:]
        u.EnumWindows(ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(cb), 0)
        if found:
            return True
        time.sleep(0.3)
    return False


def tail(path, lines=25):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:]).rstrip()
    except OSError:
        return "（没有日志）"


def build(stage, work):
    os.makedirs(stage)
    vf = os.path.join(work, "version_info.txt")
    with open(vf, "w", encoding="utf-8", newline="\n") as f:
        f.write(make_version_info.text())
    cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--windowed", "--noconfirm",
           "--name", "命令提示", "--icon", os.path.join(ROOT, "icon.ico"), "--version-file", vf,
           "--add-data", os.path.join(HERE, "commands.json") + ";.",
           "--add-data", os.path.join(HERE, "commands_extra.txt") + ";.",
           "--add-data", os.path.join(ROOT, "icon.ico") + ";.",
           "--hidden-import", "pystray._win32", "--hidden-import", "pypinyin",
           "--collect-data", "pypinyin", "--paths", HERE,
           "--distpath", stage, "--workpath", os.path.join(work, "build"), "--specpath", work,
           os.path.join(HERE, "main.py")]
    log_path = os.path.join(work, "pyinstaller.log")
    with open(log_path, "w", encoding="utf-8") as log:
        p = subprocess.run(cmd, cwd=HERE, stdout=log, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError("PyInstaller 失败：\n" + tail(log_path))
    return stage


def keep_log(work):
    try:
        dst = os.path.join(tempfile.gettempdir(), LOG_NAME)
        shutil.copy(os.path.join(work, "pyinstaller.log"), dst)
        return dst
    except OSError:
        return "（没有日志）"


def main():
    args = sys.argv[1:]
    os.chdir(HERE)
    for module in ("PyInstaller", "keyboard", "pystray", "PIL", "pypinyin"):
        if importlib.util.find_spec(module) is None:
            fail("缺少依赖 " + module + "。请运行：pip install " + module.lower())
    for name in ("main.py", "commands.json", "commands_extra.txt"):
        if not os.path.exists(os.path.join(HERE, name)):
            fail("找不到 " + os.path.join(HERE, name))
    if not os.path.exists(os.path.join(ROOT, "icon.ico")):
        fail("找不到 " + os.path.join(ROOT, "icon.ico"))
    if "--check" in args:
        say("检查通过，没有改动任何东西。当前版本 " + VERSION)
        return 0
    had_old = os.path.exists(EXE)
    stop_running()
    work = tempfile.mkdtemp(prefix="cmdhint-build-")
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    try:
        say("正在打包 " + VERSION + "，大约需要半分钟…")
        new = os.path.join(build(os.path.join(work, "dist"), work), NAME)
        got = file_version(new)
        if got != VERSION:
            raise RuntimeError("新 exe 的版本号是「%s」，应为「%s」" % (got or "读不到", VERSION))
        if os.path.getsize(new) < 15 * 1048576:
            raise RuntimeError("新 exe 只有 %.1f MB，不正常" % (os.path.getsize(new) / 1048576))
        if had_old:
            replace(EXE, PREV)
        replace(new, EXE)
    except Exception as e:
        log = keep_log(work)
        if had_old and os.path.exists(EXE):
            os.startfile(EXE)
        fail("没有打成新包，原来的程序没有改动，已重新启动。\n原因：%s\n打包日志：%s" % (e, log))
    if "--no-start" in args:
        say("已换成 " + VERSION + "，按要求没有启动。")
        if had_old:
            say("上一版留在了 " + PREV)
        return 0
    os.startfile(EXE)
    if bar_visible(BAR_TIMEOUT):
        say("完成：版本 " + VERSION + "，%.1f MB。新程序已启动，提示条正常出现。" % (
            os.path.getsize(EXE) / 1048576))
        if had_old:
            say("上一版留在了 " + PREV)
        return 0
    log = keep_log(work)
    say("新版没能正常出现提示条，正在恢复上一版…")
    stop_running()
    if had_old and os.path.exists(PREV):
        replace(PREV, EXE)
        os.startfile(EXE)
        if bar_visible(BAR_TIMEOUT):
            fail("新版启动失败，已恢复并重新启动上一版。请把这个信息告诉我。\n打包日志：" + log)
        fail("新版启动失败，上一版也没能启动。请手动打开 " + EXE)
    fail("新版启动失败，而且没有上一版可恢复。请手动打开 " + EXE + "\n打包日志：" + log)


if __name__ == "__main__":
    main()
