# -*- coding: utf-8 -*-
"""运维命令速查 · 桌面版启动器。

用本地 HTTP 服务加载页面（固定 127.0.0.1 端口，收藏和自定义命令才能持久保存），
再用 pywebview 打开一个无地址栏的原生窗口。
"""

import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview


def copy_to_clipboard(text):
    """写入 Windows 剪贴板，避免 WebView2 的剪贴板权限弹窗。"""
    cf_unicodetext = 13
    gmem_moveable = 0x0002
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
    kernel32.GlobalFree.restype = wintypes.HANDLE
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL

    payload = text.encode('utf-16-le') + b'\x00\x00'

    opened = False
    for _ in range(5):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        return False

    try:
        if not user32.EmptyClipboard():
            return False
        handle = kernel32.GlobalAlloc(gmem_moveable, len(payload))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(cf_unicodetext, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()

APP_TITLE = '运维命令速查'
APP_DIR_NAME = 'OpsCmd'
PREFERRED_PORT = 8765


def asset_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def user_data_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


def start_server(directory):
    """固定端口起本地服务；被占用时顺延，保证页面同源、localStorage 可复用。"""
    last_error = None
    for port in range(PREFERRED_PORT, PREFERRED_PORT + 20):
        try:
            handler = partial(QuietHandler, directory=directory)
            httpd = ThreadingHTTPServer(('127.0.0.1', port), handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            return httpd, port
        except OSError as exc:
            last_error = exc
    raise RuntimeError('本地服务端口都被占用：%s' % last_error)


class Api:
    """暴露给页面的桌面能力：原生文件对话框。"""

    def __init__(self):
        self._window = None

    def copy_text(self, text):
        return copy_to_clipboard(str(text))

    def export_backup(self, text):
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory=str(Path.home() / 'Desktop'),
            save_filename='opscmd-backup-%s.json' % date.today().isoformat(),
            file_types=('JSON 文件 (*.json)',),
        )
        path = result[0] if isinstance(result, (list, tuple)) else result
        if not path:
            return ''
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        return path

    def import_backup(self):
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=('JSON 文件 (*.json)',),
        )
        path = result[0] if isinstance(result, (list, tuple)) else result
        if not path:
            return ''
        with open(path, 'r', encoding='utf-8-sig') as fh:
            return fh.read()


def main():
    directory = asset_dir()
    server, port = start_server(directory)
    api = Api()

    icon = os.path.join(directory, 'icon.ico')
    window = webview.create_window(
        APP_TITLE,
        'http://127.0.0.1:%d/index.html' % port,
        js_api=api,
        width=1120,
        height=820,
        min_size=(720, 520),
        background_color='#070b10',
        text_select=True,
        zoomable=True,
    )
    api._window = window

    try:
        webview.start(
            private_mode=False,
            storage_path=os.path.join(user_data_dir(), 'webview'),
            icon=icon if os.path.exists(icon) else None,
            debug='--debug' in sys.argv,
        )
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()