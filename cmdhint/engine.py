import os

import keyboard

import winapi

MOD_WORDS = ("ctrl", "shift", "alt", "windows", "lock")
RESET_KEYS = {
    "tab", "up", "down", "left", "right", "home", "end",
    "delete", "page up", "page down", "insert",
}
MAX_BUF = 200


class Engine:
    def __init__(self, cfg, out_queue):
        self.cfg = cfg
        self.q = out_queue
        self.terminals = set(cfg["terminals"])
        self.exclude = set(cfg["exclude"])
        self.scope_all = cfg.get("scope", "all") == "all"
        self.buf = ""
        self.comp = 0
        self.paused = False
        self.injecting = False
        self.filling = False
        self.asking = False
        self.visible_count = 0
        self.hwnd = 0
        self.tid = 0
        self.term = False
        self.proc = ""
        self.blocked_up = set()

    def start(self):
        keyboard.hook(self.on_event, suppress=True)

    def stop(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def sync_fg(self):
        hwnd, tid, pid = winapi.foreground()
        if hwnd == self.hwnd:
            return False
        self.hwnd, self.tid = hwnd, tid
        name = winapi.process_name(pid)
        self.proc = name
        if pid == os.getpid():
            self.term = False
        elif self.scope_all:
            self.term = name not in self.exclude
        else:
            self.term = name in self.terminals
        self.buf = ""
        self.comp = 0
        return True

    def on_event(self, e):
        try:
            return self._on_event(e)
        except Exception:
            return True

    def _block(self, sc):
        self.blocked_up.add(sc)
        return False

    def _on_event(self, e):
        sc = e.scan_code
        name = (e.name or "").lower()
        if e.event_type == "up":
            if sc in self.blocked_up:
                self.blocked_up.discard(sc)
                return False
            return True
        ctrl = winapi.key_down(0x11)
        alt = winapi.key_down(0x12)
        win = winapi.key_down(0x5B) or winapi.key_down(0x5C)
        if ctrl and alt and name == "p":
            self.q.put(("toggle",))
            return self._block(sc)
        if self.injecting or self.paused:
            return True
        if self.sync_fg():
            self.filling = False
            self.q.put(("ctx",))
        if self.asking:
            return True
        if self.filling:
            return self._fill_key(sc, name, ctrl, alt, win)
        if not self.term:
            return True
        if any(w in name for w in MOD_WORDS):
            return True
        if ctrl and alt and name in ("a", "e", "x", "q"):
            self.q.put(("ai", self.buf) if name == "a" else (
                {"e": "err", "x": "explain", "q": "ask"}[name],))
            return self._block(sc)
        if ctrl and alt and name in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
            idx = int(name) - 1
            if idx < self.visible_count:
                self.q.put(("pick", idx))
                return self._block(sc)
        if name == "backspace":
            if ctrl or alt:
                self.comp = 0
                self._set("")
            else:
                self.comp = max(self.comp - 1, 0)
                self._set(self.buf[:-1])
            return True
        if name == "enter":
            if self.comp:
                self.comp = 0
                return True
            self._set("")
            return True
        if name == "esc":
            if self.comp:
                n, self.comp = self.comp, 0
                self._set(self.buf[:-n])
            else:
                self._set("")
            return True
        if name in RESET_KEYS or ctrl or alt or win:
            self.comp = 0
            self._set("")
            return True
        ch = winapi.char_for_scan(sc, self.tid)
        if not ch and len(name) == 1 and name.isprintable():
            ch = name
        if not ch and name == "space":
            ch = " "
        if not ch:
            return True
        if self.comp and (ch == " " or ch in "123456789"):
            self.comp = 0
            self._set("")
            return True
        if ch.isascii() and (ch.islower() or (ch == "'" and self.comp)):
            if self.comp or winapi.ime_chinese(self.hwnd):
                self.comp += 1
        if len(self.buf) >= MAX_BUF:
            self.comp = 0
            self._set("")
        else:
            self._set(self.buf + ch)
        return True

    def _fill_key(self, sc, name, ctrl, alt, win):
        if any(w in name for w in MOD_WORDS):
            return True
        if ctrl and not alt and name == "v":
            self.q.put(("fill_key", "paste"))
            return self._block(sc)
        if name in ("enter", "esc", "tab", "backspace"):
            self.q.put(("fill_key", name))
            return self._block(sc)
        ch = winapi.char_for_scan(sc, self.tid)
        if not ch and len(name) == 1 and name.isprintable():
            ch = name
        if not ch and name == "space":
            ch = " "
        if ch and not (ctrl or alt or win):
            self.q.put(("fill_char", ch))
            return self._block(sc)
        self.filling = False
        self.buf = ""
        self.q.put(("fill_cancel", self.hwnd))
        return True

    def _set(self, value):
        if value == self.buf:
            return
        self.buf = value
        self.q.put(("buf", value, self.hwnd))
