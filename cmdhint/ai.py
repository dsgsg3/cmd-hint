import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

CREATE_NO_WINDOW = 0x08000000

_cache = {}


def _resolve(exe):
    found = shutil.which(exe)
    if found:
        return found
    alt = os.path.join(os.path.expanduser("~"), ".kimi-code", "bin", exe + ".exe")
    return alt if os.path.exists(alt) else exe


def _run_cli(prompt, cfg):
    args = [a.replace("{prompt}", prompt) for a in cfg["ai_cmd"]]
    args[0] = _resolve(args[0])
    if args[0].lower().endswith((".cmd", ".bat")):
        args = ["cmd", "/c"] + args
    try:
        p = subprocess.run(
            args, capture_output=True, stdin=subprocess.DEVNULL,
            cwd=tempfile.gettempdir(), creationflags=CREATE_NO_WINDOW,
            timeout=cfg["ai_timeout"], encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise RuntimeError("找不到 AI 命令：" + cfg["ai_cmd"][0])
    except subprocess.TimeoutExpired:
        raise RuntimeError("AI 响应超时")
    return (p.stdout or "") or (p.stderr or "")


def _post(url, payload, cfg):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + cfg["api_key"],
        "User-Agent": "CmdHint/1.0",
    })
    with urllib.request.urlopen(req, timeout=cfg["ai_timeout"]) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _http_error(e):
    detail = ""
    try:
        detail = json.loads(e.read().decode("utf-8", errors="replace"))["error"]["message"]
    except Exception:
        pass
    return RuntimeError("API 返回 %d %s" % (e.code, detail[:60]))


def _net_error(e):
    if isinstance(e, TimeoutError):
        return RuntimeError("AI 响应超时")
    return RuntimeError("连不上 API：%s" % getattr(e, "reason", e))


def _run_api(prompt, cfg):
    base = cfg["api_base_url"].rstrip("/")
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    payload = {
        "model": cfg["api_model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": False,
    }
    fast = dict(payload, thinking={"type": "disabled"})
    try:
        data = _post(url, fast, cfg)
    except urllib.error.HTTPError as e:
        if e.code not in (400, 422):
            raise _http_error(e)
        try:
            data = _post(url, payload, cfg)
        except urllib.error.HTTPError as e2:
            raise _http_error(e2)
        except (urllib.error.URLError, TimeoutError) as e2:
            raise _net_error(e2)
    except (urllib.error.URLError, TimeoutError) as e:
        raise _net_error(e)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("API 返回格式异常")


def _parse(out, limit=5):
    items = []
    for raw in out.splitlines():
        line = raw.strip().lstrip("•*-· 	").strip()
        m = re.match(r"(?i)COMMAND\s*\d*\s*[:：]\s*(.+)", line)
        if m:
            cmd = m.group(1).strip().strip("`").strip()
            if cmd and all(cmd != c for c, _ in items):
                items.append([cmd, ""])
            continue
        n = re.match(r"(?i)NOTE\s*\d*\s*[:：]\s*(.+)", line)
        if n and items and not items[-1][1]:
            items[-1][1] = n.group(1).strip()
    return [(c, d) for c, d in items[:limit]]


def _complete(prompt, cfg):
    use_api = bool(cfg.get("api_key") and cfg.get("api_base_url") and cfg.get("api_model"))
    key = (prompt, cfg.get("api_model") if use_api else tuple(cfg["ai_cmd"]))
    if key in _cache:
        return _cache[key]
    out = _run_api(prompt, cfg) if use_api else _run_cli(prompt, cfg)
    if len(_cache) > 300:
        _cache.clear()
    _cache[key] = out
    return out


def _clean(text, limit=900):
    text = re.sub(r"```[a-zA-Z]*", "", text)
    lines = [re.sub(r"^\s*[-•*·]\s+", "", ln).rstrip() for ln in text.splitlines()]
    out = []
    for ln in lines:
        if not ln and (not out or not out[-1]):
            continue
        out.append(ln)
    text = "\n".join(out).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def ask(query, cfg):
    out = _complete(cfg["ai_prompt"].replace("{query}", query), cfg)
    items = _parse(out)
    if not items:
        tail = out.strip().splitlines()
        raise RuntimeError("AI 没有返回命令：" + (tail[-1][:60] if tail else "无输出"))
    return items


def ask_free(question, cfg):
    out = _complete(cfg["ask_prompt"].replace("{query}", question), cfg)
    m = re.search(r"(?is)ANSWER\s*[:：]\s*(.+?)(?=\n\s*[•*-]?\s*(?:COMMAND|NOTE)\b|\Z)", out)
    answer = _clean(m.group(1), 600) if m else ""
    items = _parse(out)
    if not answer and not items:
        tail = out.strip().splitlines()
        raise RuntimeError("AI 没有给出回答：" + (tail[-1][:60] if tail else "无输出"))
    return answer, items


def explain(command, cfg):
    return _clean(_complete(cfg["explain_prompt"].replace("{command}", command), cfg))


def analyze_error(error, cfg):
    out = _complete(cfg["error_prompt"].replace("{error}", error[-4000:]), cfg)
    m = re.search(r"(?is)CAUSE\s*[:：]\s*(.+?)(?=\n\s*COMMAND\b|\Z)", out)
    cause = _clean(re.sub(r"\s*\n\s*", " ", m.group(1)) if m else out, 300)
    return cause, _parse(out)
