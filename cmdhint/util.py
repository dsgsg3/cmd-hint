import json
import os
import re
import sys
import unicodedata
import winreg

import config

APP_NAME = "CmdHint"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STATE_PATH = os.path.join(config.APP_DIR, "state.json")
_SEPARATORS = re.compile(r"\|\||&&|[|;&]")


_BRACES = re.compile(r"\{\{(.+?)\}\}")
_TEMPLATE = re.compile(r"\s*(\.|(json|range|println|with|if)\s|end\b)")


def _is_param(raw):
    """{{容器}} is a value the user must supply; {{.Names}} / {{json .}} are Go templates."""
    return not _TEMPLATE.match(raw)


def placeholders(cmd):
    out = []
    for m in _BRACES.finditer(cmd):
        if _is_param(m.group(1)) and m.group(1).strip() not in out:
            out.append(m.group(1).strip())
    return out


def build_cmd(cmd, names, vals, cur=-1):
    def rep(m):
        name = m.group(1).strip()
        if not _is_param(m.group(1)):
            return m.group(0)
        if name in names and vals[names.index(name)]:
            return vals[names.index(name)] + ("▏" if names.index(name) == cur else "")
        return "<%s>" % name
    return _BRACES.sub(rep, cmd)


def fill_placeholders(cmd):
    return build_cmd(cmd, [], [])


_DANGER = re.compile(r"""(?xi)
    \brm\s+(-\w+\s+)*(-\w*[rf]\w*|--recursive|--force)\b
  | \bfind\b.*\s-delete\b | \bxargs\s+(-\w+\s+)*rm\b
  | \bmkfs(\.\w+)?\b | \bshred\b | \bwipe\b | \bdd\s+if=
  | (>|of=)\s*/dev/(sd|hd|vd|nvme|xvd|mmcblk)
  | \bdrop\s+(database|table|index|user|schema)\b | \btruncate\b | \bdelete\s+from\b
  | \bflushall\b | \bflushdb\b | \breset\s+master\b | \bchmod\s+(-R\s+)?[0-7]*777\b
  | :\(\)\s*\{
  | \bkill\s+(-9|-kill)\b | \bpkill\s+(-9|-kill)\b | \bkillall\b
  | \btaskkill\b.*\s/f\b | remove-item\b.*-force | stop-process\b.*-force
  | \bgit\s+(push\b.*(\s-f\b|\s--force(?!-with-lease)\b|\s--delete\b)
             |reset\s+--hard|clean\s+-\w*f|(?-i:branch\s+-D\b)|filter-repo)
  | \bdocker\s+(rm\s+-\w*f|kill\b|rmi\b|volume\s+rm
             |(system|image|container|volume|network)\s+prune|compose\s+down\b.*\s-v\b)
  | \bkubectl\s+delete\b | \bhelm\s+uninstall\b
  | \bterraform\s+(destroy\b|apply\b.*-auto-approve)
  | (?:^|[;&|]\s*)(?:sudo\s+)?(shutdown|reboot|poweroff|halt)\b(?!\s+[-/][ca]\b) | \binit\s+[06]\b
  | \biptables\s+-F\b | \bufw\s+disable\b | \buserdel\b | \bcrontab\s+-r\b
  | drop_caches | \b(rd|rmdir)\s+/s\b | \bdel\s+/[fq]\b | \breg\s+delete\b
  | \bformat\s+[a-z]: | format-volume | clear-disk
  | (\|\|?)\s*(ba|z|k)?sh\b
""")


def is_dangerous(cmd):
    return bool(_DANGER.search(cmd))


def split_query(buf):
    """Return (text to match, index in buf where it starts).

    Only the last pipeline segment is matched, and a leading `sudo` is skipped,
    so inserting a suggestion replaces just that part of the typed line."""
    start = 0
    for m in _SEPARATORS.finditer(buf):
        start = m.end()
    seg = buf[start:]
    rest = seg.lstrip()
    start += len(seg) - len(rest)
    m = re.match(r"sudo\s+", rest)
    if m:
        start += m.end()
    return buf[start:], start


def _width(ch):
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def clip(text, maxw, tail=False):
    if sum(_width(c) for c in text) <= maxw:
        return text
    out, w = [], 0
    for ch in (reversed(text) if tail else text):
        cw = _width(ch)
        if w + cw > maxw - 1:
            break
        out.append(ch)
        w += cw
    if tail:
        return "…" + "".join(reversed(out))
    return "".join(out) + "…"


def fit(text, font, px):
    if px <= 12:
        return ""
    if font.measure(text) <= px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid] + "…") <= px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"


def fit_tail(text, font, px):
    if px <= 12:
        return ""
    if font.measure(text) <= px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure("…" + text[len(text) - mid:]) <= px:
            lo = mid
        else:
            hi = mid - 1
    return "…" + text[len(text) - lo:]


def autostart_command():
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return '"%s" "%s"' % (pyw, main)


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(update):
    data = load_state()
    data.update(update)
    os.makedirs(config.APP_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
