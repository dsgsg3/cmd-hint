import tkinter as tk
import tkinter.font as tkfont

import winapi
from util import fill_placeholders, fit, fit_tail, load_state, save_state

BG = "#1b1e26"
HEAD = "#14161c"
PANEL = "#12141a"
FG = "#e8eaf0"
DIM = "#8b93a7"
ACC = "#5aa9ff"
RED = "#ff6b6b"
GREEN = "#4cd964"
AMBER = "#ffb454"
UI = "Microsoft YaHei UI"
MIN_W, MAX_W, MIN_ROWS, MAX_ROWS = 460, 2400, 3, 9
TAG_W = 44


def _int(v, lo, hi, default):
    return max(lo, min(hi, v)) if isinstance(v, int) and not isinstance(v, bool) else default


class Bar:
    def __init__(self, root, n_rows, on_resize=None):
        self.on_resize = on_resize
        st = load_state()
        self.w = _int(st.get("w"), MIN_W, MAX_W, 640)
        self.n_rows = _int(st.get("rows"), MIN_ROWS, MAX_ROWS, _int(n_rows, MIN_ROWS, MAX_ROWS, 5))
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=ACC)
        mk = lambda fam, size, bold=False: tkfont.Font(
            root=root, family=fam, size=size, weight="bold" if bold else "normal")
        self.f_cmd, self.f_typed = mk("Consolas", 10, True), mk("Consolas", 10)
        self.f_ui, self.f_small, self.f_badge = mk(UI, 9), mk(UI, 8), mk(UI, 8, True)
        self.rh = max(self.f_cmd.metrics("linespace"), self.f_ui.metrics("linespace")) + 8
        self._last = ("", DIM, "", [], "", DIM, "", False)
        self._drag = self._rs = None
        self.shown = False
        self._build()
        self._paint()
        self.top.bind_all("<ButtonPress-1>", self._press)
        self.top.bind_all("<B1-Motion>", self._move)
        self.top.bind_all("<ButtonRelease-1>", self._release)
        self.top.update_idletasks()
        self.hwnd = winapi.root_hwnd(self.top)
        winapi.make_noactivate(self.hwnd)
        x, y = self._initial_pos()
        self._pos = (x, y)
        self.top.geometry("%dx%d+%d+%d" % (self.w, self.top.winfo_reqheight(), x, y))
        winapi.show_noactivate(self.hwnd, x, y)
        self.shown = True

    def _build(self):
        body = tk.Frame(self.top, bg=BG)
        body.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(body, bg=HEAD)
        head.pack(fill="x")
        self.dot = tk.Label(head, text="●", bg=HEAD, fg=DIM, font=self.f_ui)
        self.dot.pack(side="left", padx=(8, 4))
        tk.Label(head, text="命令提示", bg=HEAD, fg=ACC, font=self.f_badge).pack(side="left")
        self.state = tk.Label(head, bg=HEAD, fg=DIM, font=self.f_ui)
        self.state.pack(side="right", padx=8)
        self.typed = tk.Label(head, bg=HEAD, fg=FG, font=self.f_typed, anchor="w")
        self.typed.pack(side="left", padx=(12, 0), pady=4)
        self.entry = tk.Entry(head, bg=BG, fg=FG, insertbackground=ACC, font=self.f_ui, relief="flat",
                              highlightthickness=1, highlightbackground=ACC, highlightcolor=ACC)
        self.on_submit = self.on_cancel = None
        self.entry.bind("<Return>", lambda e: self.on_submit and self.on_submit(self.entry.get()) or "break")
        self.entry.bind("<Escape>", lambda e: self.on_cancel and self.on_cancel() or "break")
        self.asking = False
        self.area = tk.Frame(body, bg=BG)
        self.area.pack()
        self.area.grid_propagate(False)
        self.rows = []
        for i in range(MAX_ROWS):
            fr = [tk.Frame(self.area, bg=BG) for _ in range(3)]
            for f in fr:
                f.pack_propagate(False)
            tag = tk.Label(fr[0], bg=BG, fg=ACC, font=self.f_small, anchor="w")
            cmd = tk.Label(fr[1], bg=BG, fg=FG, font=self.f_cmd, anchor="w")
            badge = tk.Label(fr[1], text="★推荐", bg=GREEN, fg=HEAD, font=self.f_badge, padx=4)
            desc = tk.Label(fr[2], bg=BG, fg=DIM, font=self.f_ui, anchor="w")
            tag.pack(fill="both", expand=True)
            cmd.pack(side="left", fill="both", expand=True)
            desc.pack(fill="both", expand=True)
            fr[0].grid(row=i, column=0, padx=(8, 0))
            fr[1].grid(row=i, column=1)
            fr[2].grid(row=i, column=2, padx=(0, 8))
            self.rows.append((fr, tag, cmd, badge, desc))
        self.msg = tk.Label(self.area, bg=BG, font=self.f_ui, anchor="w")
        self.detail = tk.Label(body, bg=PANEL, fg=FG, font=self.f_ui, anchor="nw",
                               justify="left", padx=10, pady=6)
        self.foot = tk.Frame(body, bg=HEAD)
        self.foot.pack(fill="x")
        self.hint = tk.Label(self.foot, bg=HEAD, fg=DIM, font=self.f_small, anchor="w")
        self.hint.pack(side="left", padx=10)
        self.grip = tk.Label(self.foot, text="◢", bg=HEAD, fg=ACC, font=self.f_ui, cursor="size_nw_se")
        self.grip.pack(side="right", padx=(0, 2))
        self.grip.bind("<ButtonPress-1>", self._rs_start)
        self.grip.bind("<B1-Motion>", self._rs_move)
        self.grip.bind("<ButtonRelease-1>", self._rs_end)

    def render(self, typed, dot, state, rows, message="", msg_color=DIM, detail="", detail_head=False):
        self._last = (typed, dot, state, rows, message, msg_color, detail, detail_head)
        self._paint()

    def _paint(self):
        typed, dot, state, rows, message, msg_color, detail, head = self._last
        inner = self.w - 2
        self.area.config(width=inner, height=self.n_rows * self.rh)
        cmd_px = int((inner - TAG_W - 16) * 0.58)
        desc_px = inner - TAG_W - 16 - cmd_px
        self.dot.config(fg=dot)
        self.state.config(text=state, fg=dot)
        self.typed.config(text=fit_tail(typed, self.f_typed, self.w - 230))
        badge_w = self.f_badge.measure("★推荐") + 14
        shown = rows[:self.n_rows]
        for i, (fr, tag, cmd, badge, desc) in enumerate(self.rows):
            if i >= self.n_rows or i >= len(shown):
                for f in fr:
                    f.grid_remove()
                continue
            r = shown[i]
            color = AMBER if r.get("warn") else (RED if r.get("danger") else FG)
            for f, wd in zip(fr, (TAG_W, cmd_px, desc_px)):
                f.config(width=wd, height=self.rh)
                f.grid()
            tag.config(text="[%d]" % (i + 1))
            room = cmd_px - 8 - (badge_w if r.get("rec") else 0)
            text = ("⚠ " if r.get("danger") else "") + fill_placeholders(r["cmd"])
            cmd.config(text=fit(text, self.f_cmd, room), fg=color)
            if r.get("rec"):
                badge.pack(side="right", padx=(6, 0))
            else:
                badge.pack_forget()
            desc.config(text=fit(r.get("desc", ""), self.f_ui, desc_px - 10),
                        fg=AMBER if r.get("warn") else DIM)
        if message and not shown:
            self.msg.config(text=fit(message, self.f_ui, inner - 24), fg=msg_color)
            self.msg.place(x=10, y=6)
        else:
            self.msg.place_forget()
        if detail:
            if head:
                self.detail.config(font=self.f_cmd, wraplength=0, height=1,
                                   text=fit(detail, self.f_cmd, self.w - 36))
            else:
                wrap = self.w - 36
                lines = sum(max(1, -(-self.f_ui.measure(s) // wrap)) for s in detail.split("\n"))
                self.detail.config(font=self.f_ui, wraplength=wrap, height=min(lines, 12), text=detail)
            self.detail.pack(fill="x", before=self.foot)
        else:
            self.detail.pack_forget()
        last = min(max(len(shown), 1), self.n_rows) if shown else self.n_rows
        self.hint.config(text=fit("Ctrl+Alt+1~%d 插入｜A 问 AI｜E 分析报错｜X 讲解｜P 暂停" % last,
                                  self.f_small, self.w - 60))
        self.top.update_idletasks()
        need = self.top.winfo_reqheight()
        if self.shown and self.top.winfo_height() != need:
            self.top.geometry("%dx%d+%d+%d" % ((self.w, need) + self._pos))

    def start_input(self, placeholder_hwnd=None):
        self.asking = True
        self.typed.pack_forget()
        self.entry.delete(0, "end")
        self.entry.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=4, ipady=2)
        winapi.clear_noactivate(self.hwnd)
        self.top.update_idletasks()
        winapi.force_foreground(self.hwnd)
        self.entry.focus_force()

    def stop_input(self, give_back=0):
        if not self.asking:
            return
        self.asking = False
        self.entry.pack_forget()
        self.typed.pack(side="left", padx=(12, 0), pady=4)
        winapi.make_noactivate(self.hwnd)
        if give_back:
            winapi.force_foreground(give_back)

    def keep_topmost(self):
        winapi.keep_topmost(self.hwnd)

    def _clamp(self, x, y):
        l, t, r, b = winapi.virtual_screen()
        w = self.top.winfo_reqwidth()
        return max(l - w + 80, min(x, r - 80)), max(t, min(y, b - 40))

    def _initial_pos(self):
        st = load_state()
        if isinstance(st.get("x"), int) and isinstance(st.get("y"), int):
            return self._clamp(st["x"], st["y"])
        wl, wt, _, _ = winapi.work_area(self.hwnd)
        return wl + 16, wt + 16

    def _press(self, e):
        self._drag = (e.x_root, e.y_root, self.top.winfo_x(), self.top.winfo_y())

    def _move(self, e):
        if self._drag:
            x0, y0, wx, wy = self._drag
            x, y = self._clamp(wx + e.x_root - x0, wy + e.y_root - y0)
            self.top.geometry("+%d+%d" % (x, y))
            self._pos = (x, y)

    def _release(self, e):
        if self._drag:
            self._drag = None
            save_state({"x": self.top.winfo_x(), "y": self.top.winfo_y()})

    def _rs_start(self, e):
        self._rs = (e.x_root, e.y_root, self.w, self.n_rows)
        return "break"

    def _rs_move(self, e):
        if not self._rs:
            return "break"
        x0, y0, w0, r0 = self._rs
        w = _int(w0 + e.x_root - x0, MIN_W, MAX_W, w0)
        rows = _int(r0 + round((e.y_root - y0) / self.rh), MIN_ROWS, MAX_ROWS, r0)
        if w != self.w or rows != self.n_rows:
            changed = rows != self.n_rows
            self.w, self.n_rows = w, rows
            if changed and self.on_resize:
                self.on_resize()
            self._paint()
            self.top.geometry("%dx%d+%d+%d" % ((self.w, self.top.winfo_reqheight()) + self._pos))
        return "break"

    def _rs_end(self, e):
        if self._rs:
            self._rs = None
            save_state({"w": self.w, "rows": self.n_rows})
        return "break"
