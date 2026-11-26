import ctypes
import os
import time
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t

user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.MapVirtualKeyExW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p]
user32.MapVirtualKeyExW.restype = wt.UINT
user32.ToUnicodeEx.argtypes = [wt.UINT, wt.UINT, ctypes.c_char_p, wt.LPWSTR,
                               ctypes.c_int, wt.UINT, ctypes.c_void_p]
user32.ToUnicodeEx.restype = ctypes.c_int
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.MonitorFromWindow.restype = ctypes.c_void_p
user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.SendInput.restype = wt.UINT
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short
kernel32.GetCurrentThreadId.restype = wt.DWORD
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND),
                ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND),
                ("hwndMenuOwner", wt.HWND), ("hwndMoveSize", wt.HWND),
                ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_BACK = 0x08


def foreground():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0, 0, 0
    pid = wt.DWORD()
    tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return hwnd, tid, pid.value


def process_name(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def char_for_scan(scan_code, tid):
    layout = user32.GetKeyboardLayout(tid)
    vk = user32.MapVirtualKeyExW(scan_code, 3, layout)
    if not vk:
        return ""
    state = (ctypes.c_ubyte * 256)()
    if key_down(0x10):
        state[0x10] = 0x80
    if user32.GetKeyState(0x14) & 1:
        state[0x14] = 1
    buf = ctypes.create_unicode_buffer(8)
    n = user32.ToUnicodeEx(vk, scan_code, ctypes.cast(state, ctypes.c_char_p),
                           buf, 8, 0x4, layout)
    if n == 1 and buf[0].isprintable():
        return buf[0]
    return ""


def window_rect(hwnd):
    r = wt.RECT()
    if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r.left, r.top, r.right, r.bottom
    return None


def work_area(hwnd):
    mon = user32.MonitorFromWindow(hwnd, 2)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def caret_pos(tid):
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)) or not info.hwndCaret:
        return None
    r = info.rcCaret
    if r.right - r.left <= 0 and r.bottom - r.top <= 0:
        return None
    pt = wt.POINT(r.left, r.bottom)
    user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt))
    return pt.x, pt.y


def make_noactivate(hwnd):
    ex = user32.GetWindowLongPtrW(hwnd, -20)
    user32.SetWindowLongPtrW(hwnd, -20, ex | 0x08000000 | 0x80 | 0x8)


def show_noactivate(hwnd, x, y):
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), x, y, 0, 0, 0x0001 | 0x0010)
    user32.ShowWindow(hwnd, 4)


def keep_topmost(hwnd):
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


def virtual_screen():
    gm = user32.GetSystemMetrics
    left, top = gm(76), gm(77)
    return left, top, left + gm(78), top + gm(79)


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


def clear_noactivate(hwnd):
    ex = user32.GetWindowLongPtrW(hwnd, -20)
    user32.SetWindowLongPtrW(hwnd, -20, ex & ~0x08000000)


def hide_window(hwnd):
    user32.ShowWindow(hwnd, 0)


def root_hwnd(widget):
    return user32.GetAncestor(widget.winfo_id(), 2) or widget.winfo_id()


def _key_input(vk=0, scan=0, flags=0):
    i = INPUT()
    i.type = INPUT_KEYBOARD
    i.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def send_backspaces(n):
    while n > 0:
        k = min(n, 40)
        evs = []
        for _ in range(k):
            evs.append(_key_input(vk=VK_BACK))
            evs.append(_key_input(vk=VK_BACK, flags=KEYEVENTF_KEYUP))
        _send(evs)
        n -= k
        time.sleep(0.01)


def send_text(text):
    data = text.encode("utf-16-le")
    units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
    for start in range(0, len(units), 30):
        evs = []
        for u in units[start:start + 30]:
            evs.append(_key_input(scan=u, flags=KEYEVENTF_UNICODE))
            evs.append(_key_input(scan=u, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        _send(evs)
        time.sleep(0.01)


def send_vk(vk):
    _send([_key_input(vk=vk), _key_input(vk=vk, flags=KEYEVENTF_KEYUP)])


def wait_modifiers_released(timeout=1.5):
    end = time.time() + timeout
    while time.time() < end and (key_down(0x11) or key_down(0x12) or key_down(0x5B) or key_down(0x5C)):
        time.sleep(0.02)


def force_foreground(hwnd):
    fg = user32.GetForegroundWindow()
    cur = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    if fg_tid and fg_tid != cur:
        attached = bool(user32.AttachThreadInput(cur, fg_tid, True))
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur, fg_tid, False)


def wait_foreground(hwnd, timeout=1.0):
    end = time.time() + timeout
    while time.time() < end:
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.02)
    return False


imm32 = ctypes.WinDLL("imm32", use_last_error=True)
imm32.ImmGetDefaultIMEWnd.argtypes = [wt.HWND]
imm32.ImmGetDefaultIMEWnd.restype = wt.HWND
user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT,
                                       wt.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t


def ime_chinese(hwnd):
    """True when the foreground window's IME is open and in native (Chinese) mode."""
    try:
        ime = imm32.ImmGetDefaultIMEWnd(hwnd)
        if not ime:
            return False
        out = ctypes.c_size_t()

        def ask(wparam):
            ok = user32.SendMessageTimeoutW(ime, 0x283, wparam, 0, 0x2, 40, ctypes.byref(out))
            return out.value if ok else None

        opened, conv = ask(5), ask(1)
        return bool(opened) and conv is not None and bool(conv & 1)
    except Exception:
        return False


def single_instance(name):
    h = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183, h
