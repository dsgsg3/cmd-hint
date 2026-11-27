import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import ai
import config
import update
import winapi
from bar import ACC, AMBER, DIM, GREEN, RED, Bar
from engine import Engine
from matcher import Matcher, resource_path
from util import (APP_NAME, autostart_enabled, bump_freq, build_cmd, caret_left_steps,
                  is_dangerous, placeholders, set_autostart, split_query)
from version import VERSION


class App:
    def __init__(self):
        config.save_defaults_if_missing()
        self.cfg = config.load()
        self.matcher = Matcher()
        self.matcher.add_custom(self.cfg.get("custom_commands", []))
        self.cmd_mtime = self._cmd_mtime()
        self.reloading = False
        self.q = queue.Queue()
        self.engine = Engine(self.cfg, self.q)
        self.root = tk.Tk()
        self.root.withdraw()
        self.bar = Bar(self.root, self.cfg["max_items"], self.on_resize)
        self.shown = []
        self.query_start = 0
        self.typed = ""
        self.ai_token = 0
        self.ai_state = None
        self.detail = ""
        self.confirm = None
        self.explain_armed = False
        self.fill = None
        self.asking = False
        self.ask_back = 0
        self.ctx_hold = 0.0
        self.bar.on_submit = self.submit_question
        self.bar.on_cancel = self.end_ask
        self.bar.on_pick = self.click_pick
        self.icon = None
        self.update_ready = None
        self.update_busy = False
        self.update_next = time.time() + 20
        self.render()

    def run(self):
        self.engine.start()
        self.start_tray()
        self.root.after(25, self.pump)
        self.root.after(1000, self.tick)
        self.root.mainloop()

    def start_tray(self):
        import pystray
        from PIL import Image

        try:
            img = Image.open(resource_path("icon.ico"))
        except Exception:
            img = Image.new("RGB", (64, 64), "#5aa9ff")
        menu = pystray.Menu(
            pystray.MenuItem("暂停提示 (Ctrl+Alt+P)", lambda i, m: self.q.put(("toggle",)),
                             checked=lambda m: self.engine.paused),
            pystray.MenuItem("开机自启", lambda i, m: self.q.put(("autostart",)),
                             checked=lambda m: autostart_enabled()),
            pystray.MenuItem("打开配置文件", lambda i, m: self.q.put(("config",))),
            pystray.MenuItem("打开命令文件", lambda i, m: self.q.put(("cmdfile",))),
            pystray.MenuItem("检查更新", lambda i, m: self.q.put(("update_check",))),
            pystray.MenuItem("重启并更新", lambda i, m: self.q.put(("update_apply",)),
                             visible=lambda item: bool(self.update_ready)),
            pystray.MenuItem("退出", lambda i, m: self.q.put(("quit",))),
        )
        self.icon = pystray.Icon(APP_NAME, img, "命令提示 " + VERSION, menu)
        self.icon.run_detached()

    def pump(self):
        try:
            while True:
                self.handle(self.q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(25, self.pump)

    def _cmd_mtime(self):
        try:
            return os.stat(self.matcher.user_path).st_mtime_ns
        except OSError:
            return None

    def watch_commands(self):
        if self.reloading:
            return
        mtime = self._cmd_mtime()
        if mtime is None or mtime == self.cmd_mtime:
            return
        self.cmd_mtime = mtime
        self.reloading = True
        threading.Thread(target=self.reload_commands, daemon=True).start()

    def reload_commands(self):
        try:
            m = Matcher(user_path=self.matcher.user_path)
            m.add_custom(self.cfg.get("custom_commands", []))
            self.q.put(("reloaded", m))
        except Exception as e:
            self.q.put(("reload_failed", str(e)))
        finally:
            self.reloading = False

    def refresh_after_reload(self):
        if self.fill or self.asking:
            return
        if self.shown and self.shown[0].get("ai"):
            return
        query, self.query_start = split_query(self.typed)
        query = query.strip()
        if len(query) >= self.cfg["min_chars"]:
            self.set_shown(self.search(query))
        self.render()

    def start_update_check(self, manual):
        mode = config.load().get("update_mode", "download")
        if self.update_busy or (not manual and mode == "off"):
            return
        self.update_busy = True
        threading.Thread(target=self.update_worker, args=(manual,), daemon=True).start()

    def update_worker(self, manual):
        try:
            info = update.fetch_latest()
            if not update.is_newer(info["version"]):
                if manual:
                    self.notify("已经是最新版本 " + VERSION)
                return
            path = update.prepare(info)
            self.q.put(("update_ready", info["version"], path))
        except Exception as e:
            update.log("检查更新失败：%r" % e)
            if manual:
                self.notify("检查更新失败：" + str(e)[:100])
        finally:
            self.update_busy = False

    def notify(self, text):
        if self.icon:
            try:
                self.icon.notify(text, "命令提示")
            except Exception:
                pass

    def on_update_ready(self, version, path):
        self.update_ready = (version, path)
        self.notify("新版本 %s 已下载，右键托盘图标点「重启并更新」" % version)
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception:
                pass
        if config.load().get("update_mode") == "auto":
            self.apply_update()

    def apply_update(self):
        if not self.update_ready:
            return
        version, path = self.update_ready
        probe = os.path.join(os.path.dirname(sys.executable), ".cmd-hint-write-test")
        try:
            with open(probe, "w") as f:
                f.write("x")
            os.remove(probe)
        except OSError:
            self.notify("没有权限自动更新，请到 GitHub Releases 手动下载")
            return
        try:
            update.apply_and_restart(path)
        except Exception as e:
            self.notify("更新启动失败：" + str(e)[:100])
            return
        self.quit()

    def tick(self):
        self.bar.keep_topmost()
        self.bar.bring_into_screen()
        self.watch_commands()
        if not self.engine.paused and not self.engine.healthy():
            self.engine.restart()
        if time.time() >= self.update_next:
            self.update_next = time.time() + 6 * 3600
            self.start_update_check(False)
        if not self.engine.paused and self.engine.sync_fg():
            self.on_ctx()
        self.root.after(1000, self.tick)

    def handle(self, ev):
        kind = ev[0]
        if kind == "buf":
            self.on_buf(ev[1])
        elif kind == "ctx":
            self.on_ctx()
        elif kind == "pick":
            self.pick(ev[1])
        elif kind == "ai":
            self.ask_ai(ev[1])
        elif kind == "ai_done":
            self.on_ai_done(*ev[1:])
        elif kind == "err":
            self.analyze_error()
        elif kind == "error_done":
            self.on_error_done(*ev[1:])
        elif kind == "explain":
            self.explain()
        elif kind == "ask":
            self.begin_ask()
        elif kind == "ask_done":
            self.on_ask_done(*ev[1:])
        elif kind == "explain_done":
            self.on_explain_done(*ev[1:])
        elif kind == "fill_key":
            self.fill_key(ev[1])
        elif kind == "fill_char":
            self.fill_char(ev[1])
        elif kind == "fill_cancel":
            self.cancel_fill()
            self.on_buf("")
        elif kind == "toggle":
            self.toggle()
        elif kind == "freeze":
            self.engine.frozen = True
        elif kind == "autostart":
            set_autostart(not autostart_enabled())
        elif kind == "config":
            os.startfile(config.CONFIG_PATH)
        elif kind == "cmdfile":
            if self.matcher.user_path:
                os.startfile(self.matcher.user_path)
        elif kind == "reloaded":
            self.matcher = ev[1]
            self.reloading = False
            self.refresh_after_reload()
        elif kind == "reload_failed":
            self.reloading = False
            self.ai_state = ("err", "命令库读取失败：" + ev[1])
            self.render()
        elif kind == "update_check":
            self.start_update_check(True)
        elif kind == "update_ready":
            self.on_update_ready(*ev[1:])
        elif kind == "update_apply":
            self.apply_update()
        elif kind == "quit":
            self.quit()

    def set_shown(self, rows):
        self.shown = rows
        self.engine.visible_count = len(rows)

    def search(self, query):
        return [dict(it, danger=it["danger"] or is_dangerous(it["cmd"]))
                for it in self.matcher.search(query, self.bar.n_rows)]

    def on_resize(self):
        if self.ai_state or self.fill or not self.shown:
            return
        if self.shown and self.shown[0].get("ai"):
            return
        query, self.query_start = split_query(self.typed)
        query = query.strip()
        if len(query) >= self.cfg["min_chars"]:
            self.set_shown(self.search(query))
            self.render()

    def reset_view(self):
        self.ai_token += 1
        self.ai_state = None
        self.detail = ""
        self.confirm = None
        self.explain_armed = False

    def cancel_fill(self):
        self.fill = None
        self.engine.filling = False

    def on_ctx(self):
        if self.asking or time.time() < self.ctx_hold:
            return
        if self.ai_state and self.ai_state[0] == "wait":
            return
        self.reset_view()
        self.cancel_fill()
        self.typed = ""
        self.set_shown([])
        self.render()

    def on_buf(self, text):
        if self.asking or self.engine.paused:
            return
        self.reset_view()
        self.cancel_fill()
        self.typed = text
        query, self.query_start = split_query(text)
        query = query.strip()
        if len(query) >= self.cfg["min_chars"]:
            self.set_shown(self.search(query))
        else:
            self.set_shown([])
        self.render()

    def ai_rows(self, items, fallback):
        return [{"cmd": cmd, "desc": note or fallback, "ai": True, "rec": i == 0,
                 "danger": is_dangerous(cmd)}
                for i, (cmd, note) in enumerate(items[:self.bar.n_rows])]

    def render(self):
        eng = self.engine
        rows, detail = self.shown, self.detail
        dot, state, msg, color = GREEN, "监听中", "", DIM
        if eng.paused:
            dot, state, msg = AMBER, "已暂停", "Ctrl+Alt+P 恢复"
            rows, detail = [], ""
        elif self.fill:
            self.render_fill()
            return
        elif self.asking and not self.ai_state:
            self.bar.render("", ACC, "提问模式", [],
                            "输入问题（中文或英文），Enter 发送，Esc 取消", ACC, "")
            return
        elif not eng.term:
            dot, state, msg = DIM, "待机", "当前窗口在排除名单里，不会记录按键"
            rows, detail = [], ""
        elif self.ai_state:
            kind, text = self.ai_state
            if kind == "wait":
                dot, state, msg = ACC, "AI 思考中", text
            else:
                msg, color = text, RED
        elif self.explain_armed:
            state = "选一条讲解"
            detail = "按 Ctrl+Alt+1~%d 讲解对应命令，Esc 取消" % max(len(rows), 1)
        elif not self.typed:
            msg = "敲英文或拼音（如 neicun、cipan），这里实时提示"
        elif not rows and not detail:
            msg = "没有匹配的命令，可按 Ctrl+Alt+Q 提问，或 Ctrl+Alt+A 问 AI"
        if self.confirm and self.confirm[0] < len(rows):
            rows = [dict(r) for r in rows]
            i = self.confirm[0]
            rows[i]["warn"] = True
            rows[i]["desc"] = "⚠ 危险命令，再按一次 Ctrl+Alt+%d 确认插入" % (i + 1)
        self.bar.render(self.typed, dot, state, rows, msg, color, detail)

    def render_fill(self):
        f = self.fill
        i, names = f["i"], f["names"]
        msg = "填参数 %d/%d：<%s>    Enter 下一个，Esc 取消，留空则保留 <%s>" % (
            i + 1, len(names), names[i], names[i])
        preview = build_cmd(f["cmd"], names, f["vals"], i)
        self.bar.render(f["vals"][i], ACC, "填参数", [], msg, ACC, preview, True)

    def pick(self, idx):
        if idx >= len(self.shown):
            return
        row = self.shown[idx]
        if self.explain_armed:
            self.explain_armed = False
            self.explain_cmd(row["cmd"])
            return
        if row.get("danger") and self.confirm != (idx, row["cmd"]):
            self.confirm = (idx, row["cmd"])
            self.render()
            return
        self.confirm = None
        eng = self.engine
        comp = eng.comp
        committed = eng.buf[:len(eng.buf) - comp] if comp else eng.buf
        n = max(len(committed) - self.query_start, 0)
        if comp and len(eng.buf) - comp < self.query_start:
            n = 0
        bump_freq(row["cmd"])
        names = placeholders(row["cmd"])
        if names:
            self.fill = {"cmd": row["cmd"], "names": names, "vals": [""] * len(names),
                         "i": 0, "n": n, "comp": comp, "hwnd": eng.hwnd}
            eng.filling = True
        else:
            threading.Thread(target=self.inject, args=(row["cmd"], n, comp, eng.hwnd),
                             daemon=True).start()
        self.render()

    def click_pick(self, idx):
        if self.asking or self.fill:
            return
        hwnd = self.engine.hwnd
        winapi.force_foreground(hwnd)
        self.root.after(120, lambda: self.pick(idx))

    def inject(self, cmd, n, comp, hwnd):
        update.log("inject 开始 cmd=%r n=%s" % (cmd[:40], n))
        winapi.wait_modifiers_released()
        if winapi.foreground()[0] != hwnd:
            update.log("inject 放弃：前台已不是目标窗口")
            return
        eng = self.engine
        back = 0
        eng.injecting = True
        try:
            if comp:
                winapi.send_vk(0x1B)
                time.sleep(0.12)
            winapi.send_backspaces(n)
            winapi.send_text_slow(cmd)
            time.sleep(0.05)
            back = caret_left_steps(cmd)
            if back:
                winapi.send_left(back)
        except Exception as e:
            update.log("inject 出错：%r" % e)
            raise
        finally:
            eng.injecting = False
        update.log("inject 完成，回退 %d 步" % back)
        keep = len(eng.buf) - comp - n
        eng.comp = 0
        eng.buf = eng.buf[:max(keep, 0)] + cmd
        if back:
            self.q.put(("freeze",))
        else:
            self.q.put(("buf", eng.buf))

    def fill_char(self, ch):
        f = self.fill
        if f and len(f["vals"][f["i"]]) < 200:
            f["vals"][f["i"]] += ch
            self.render()

    def fill_key(self, key):
        f = self.fill
        if not f:
            return
        if key == "esc":
            self.cancel_fill()
        elif key in ("enter", "tab"):
            if f["i"] + 1 < len(f["names"]):
                f["i"] += 1
            else:
                self.cancel_fill()
                cmd = build_cmd(f["cmd"], f["names"], f["vals"])
                threading.Thread(target=self.inject, args=(cmd, f["n"], f["comp"], f["hwnd"]),
                                 daemon=True).start()
                return
        elif key == "backspace":
            f["vals"][f["i"]] = f["vals"][f["i"]][:-1]
        elif key == "paste":
            try:
                line = self.root.clipboard_get().splitlines()[0].strip()
            except Exception:
                line = ""
            f["vals"][f["i"]] += line[:200]
        self.render()

    def start_ai(self, waiting, done_event, fn, arg):
        self.ai_token += 1
        token = self.ai_token
        self.ai_state = ("wait", waiting)
        self.render()

        def work():
            try:
                self.q.put((done_event, token, fn(arg, self.cfg), None))
            except Exception as e:
                self.q.put((done_event, token, None, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def clear_for_ai(self):
        self.cancel_fill()
        self.confirm = None
        self.explain_armed = False
        self.set_shown([])
        self.detail = ""
        self.query_start = 0

    def ask_ai(self, text):
        text = text.strip()
        if not text:
            self.ai_state = ("err", "先输入你想做的事，再按 Ctrl+Alt+A")
            self.render()
            return
        self.clear_for_ai()
        self.start_ai("AI 思考中：" + text, "ai_done", ai.ask, text)

    def on_ai_done(self, token, items, err):
        if token != self.ai_token:
            return
        if err:
            self.ai_state = ("err", "AI 出错：" + err)
        else:
            self.ai_state = None
            self.set_shown(self.ai_rows(items, "AI 生成，执行前请确认"))
        self.render()

    def begin_ask(self):
        if self.asking or self.fill or self.engine.paused:
            return
        self.ask_back = self.engine.hwnd
        self.clear_for_ai()
        self.reset_view()
        self.asking = True
        self.engine.asking = True
        self.render()
        self.bar.start_input()
        self.root.after(250, self.check_ask_focus)

    def check_ask_focus(self):
        if not self.asking:
            return
        if winapi.foreground()[0] != self.bar.hwnd:
            self.end_ask(give_back=False)
            self.ai_state = ("err", "没能切到提问输入框，已取消（避免把字打进终端）")
            self.render()

    def end_ask(self, give_back=True):
        if not self.asking:
            return
        self.asking = False
        self.engine.asking = False
        self.ctx_hold = time.time() + 2.5
        self.bar.stop_input(self.ask_back if give_back else 0)
        self.render()

    def submit_question(self, text):
        text = text.strip()
        if not text:
            return "break"
        self.asking = False
        self.engine.asking = False
        self.ctx_hold = time.time() + 2.5
        self.bar.stop_input(self.ask_back)
        self.clear_for_ai()
        self.typed = text
        self.start_ai("AI 思考中：" + text, "ask_done", ai.ask_free, text)
        return "break"

    def on_ask_done(self, token, result, err):
        if token != self.ai_token:
            return
        if err:
            self.ai_state = ("err", "AI 出错：" + err)
        else:
            answer, items = result
            self.ai_state = None
            self.detail = answer
            self.set_shown(self.ai_rows(items, "AI 给出的命令"))
        self.render()

    def analyze_error(self):
        try:
            text = self.root.clipboard_get().strip()
        except Exception:
            text = ""
        if not text:
            self.ai_state = ("err", "剪贴板里没有文本：先复制一段报错再按 Ctrl+Alt+E")
            self.render()
            return
        self.clear_for_ai()
        self.start_ai("AI 分析报错中…", "error_done", ai.analyze_error, text)

    def on_error_done(self, token, result, err):
        if token != self.ai_token:
            return
        if err:
            self.ai_state = ("err", "AI 出错：" + err)
        else:
            self.ai_state = None
            self.detail = result[0]
            self.set_shown(self.ai_rows(result[1], "AI 给出的修复命令"))
        self.render()

    def explain(self):
        if self.fill:
            return
        if self.shown:
            self.explain_armed = not self.explain_armed
            self.confirm = None
        elif self.typed.strip():
            self.explain_cmd(self.typed.strip())
            return
        else:
            self.ai_state = ("err", "没有可讲解的命令：先敲几个字母，或等提示出来")
        self.render()

    def explain_cmd(self, cmd):
        self.detail = ""
        self.start_ai("", "explain_done", ai.explain, cmd)

    def on_explain_done(self, token, text, err):
        if token != self.ai_token:
            return
        self.ai_state = None
        self.detail = text or ("AI 出错：" + (err or "无输出"))
        self.render()

    def toggle(self):
        eng = self.engine
        eng.paused = not eng.paused
        self.cancel_fill()
        if eng.paused:
            self.set_shown([])
            self.typed = ""
        else:
            eng.hwnd = 0
            eng.sync_fg()
            self.typed = ""
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception:
                pass
        self.render()

    def quit(self):
        self.engine.stop()
        if self.icon:
            self.icon.stop()
        self.root.quit()


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--apply-update":
        sys.exit(update.run_apply(sys.argv[2], sys.argv[3]))
    update.cleanup()
    ok, _h = winapi.single_instance("Local\\CmdHintSingleton")
    if not ok:
        return
    App().run()


if __name__ == "__main__":
    main()
