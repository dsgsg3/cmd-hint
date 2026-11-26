import json
import os
import re
import sys

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:
    lazy_pinyin = None

_HAN = re.compile(r"[一-鿿]")


def _pinyin_forms(text):
    """Return (full, initials) pinyin strings for the Chinese part of text, '' if none."""
    if lazy_pinyin is None or not _HAN.search(text):
        return "", ""
    full, ini = [], []
    for chunk in re.findall(r"[一-鿿]+|[^一-鿿]+", text):
        if _HAN.match(chunk):
            full.extend(lazy_pinyin(chunk))
            ini.extend(lazy_pinyin(chunk, style=Style.FIRST_LETTER))
    return "".join(full), "".join(ini)


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def load_extra(path):
    cats, cmds = [], []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return cats, cmds
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@cat"):
            parts = line.split("¦")
            if len(parts) >= 3:
                cats.append({"id": parts[1].strip(), "label": parts[2].strip()})
            continue
        p = line.split("¦")
        if len(p) < 3:
            continue
        flags = p[4].strip() if len(p) > 4 else ""
        cmds.append({
            "cat": p[0].strip(), "cmd": p[1].strip(), "desc": p[2].strip(),
            "tags": [t.strip() for t in (p[3] if len(p) > 3 else "").split(",") if t.strip()],
            "danger": "d" in flags, "hot": "h" in flags,
        })
    return cats, cmds


class Matcher:
    def __init__(self, path=None, extra_path=None):
        with open(path or resource_path("commands.json"), encoding="utf-8") as f:
            data = json.load(f)
        extra_cats, extra_cmds = load_extra(extra_path or resource_path("commands_extra.txt"))
        have = {c["id"] for c in data["categories"]}
        data["categories"] += [c for c in extra_cats if c["id"] not in have]
        seen = {c["cmd"].strip().lower() for c in data["commands"]}
        for c in extra_cmds:
            key = c["cmd"].lower()
            if key not in seen:
                seen.add(key)
                data["commands"].append(c)
        self.cat_label = {c["id"]: c["label"] for c in data["categories"]}
        self.items = []
        for c in data["commands"]:
            self.items.append({
                "cmd": c["cmd"],
                "cmd_l": c["cmd"].lower(),
                "desc": c.get("desc", ""),
                "desc_l": c.get("desc", "").lower(),
                "tags_l": " ".join(c.get("tags", [])).lower(),
                "cat_l": self.cat_label.get(c["cat"], "").lower(),
                "danger": bool(c.get("danger")),
                "hot": bool(c.get("hot")),
            })
            it = self.items[-1]
            text = c.get("desc", "") + " " + " ".join(c.get("tags", []))
            it["py_full"], it["py_ini"] = _pinyin_forms(text)
            it["py_full_desc"], it["py_ini_desc"] = _pinyin_forms(c.get("desc", ""))

    def add_custom(self, cmds):
        for c in cmds:
            self.items.append({
                "cmd": c, "cmd_l": c.lower(), "desc": "自定义", "desc_l": "自定义",
                "tags_l": "", "cat_l": "", "danger": False, "hot": False,
                "py_full": "", "py_ini": "", "py_full_desc": "", "py_ini_desc": "",
            })

    def _score(self, it, tokens, phrase):
        cmd = it["cmd_l"]
        if len(phrase) == 1 and not cmd.startswith(phrase):
            return 0
        if cmd.startswith(phrase):
            return 100 + (3 if it["hot"] else 0)
        in_cmd = all(t in cmd for t in tokens)
        if in_cmd:
            return 60 + (10 if cmd.startswith(tokens[0]) else 0) + (3 if it["hot"] else 0)
        total = 0
        for t in tokens:
            if t in cmd:
                total += 14
            elif t in it["desc_l"]:
                total += 9
            elif t in it["tags_l"] or t in it["cat_l"]:
                total += 6
            else:
                return 0
        if phrase in it["desc_l"]:
            total += 6
        return 10 + total + (1.5 if it["hot"] else 0)

    def _pinyin_score(self, it, phrase):
        q = phrase.replace(" ", "").replace("'", "")
        if len(q) < 2 or not q.isascii() or not q.isalpha():
            return 0
        full, ini = it["py_full"], it["py_ini"]
        if not full:
            return 0
        if full.startswith(q) or it["py_full_desc"].startswith(q):
            return 40
        if q in full:
            return 30
        if len(q) >= 2 and (ini.startswith(q) or it["py_ini_desc"].startswith(q)):
            return 24
        if len(q) >= 3 and q in ini:
            return 16
        return 0

    def search(self, query, limit=5):
        phrase = " ".join(query.strip().lower().split())
        tokens = phrase.split(" ") if phrase else []
        if not tokens:
            return []
        scored = []
        for it in self.items:
            s = self._score(it, tokens, phrase)
            if s <= 0:
                s = self._pinyin_score(it, phrase)
                if s > 0 and it["hot"]:
                    s += 1.5
            if s > 0:
                scored.append((s, it))
        scored.sort(key=lambda x: (-x[0], len(x[1]["cmd"])))
        return [it for _, it in scored[:limit]]
