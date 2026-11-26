import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

import config
import winapi
from version import VERSION

API_URL = "https://api.github.com/repos/dsgsg3/cmd-hint/releases/latest"
ASSET_RE = re.compile(r"^CmdHint-(\d+\.\d+\.\d+\.\d+)\.exe$", re.I)
UA = "CmdHint/" + VERSION


def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(candidate, current=VERSION):
    a, b = parse_version(candidate), parse_version(current)
    return bool(a and b and a > b)


def update_dir():
    return os.path.join(config.APP_DIR, "update")


def _opener():
    proxy = config.load().get("update_proxy") or ""
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    else:
        handler = urllib.request.ProxyHandler()
    return urllib.request.build_opener(handler)


def fetch_latest(timeout=25):
    req = urllib.request.Request(API_URL, headers={"User-Agent": UA,
                                                   "Accept": "application/vnd.github+json"})
    with _opener().open(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    version = parse_version(data.get("tag_name") or "")
    if not version:
        raise RuntimeError("发布页的版本号看不懂：" + str(data.get("tag_name")))
    asset = None
    for a in data.get("assets") or []:
        if ASSET_RE.match(a.get("name") or ""):
            asset = a
            break
    if not asset:
        raise RuntimeError("最新发布里没有找到 exe 附件")
    return {
        "version": ".".join(str(x) for x in version),
        "url": asset.get("browser_download_url") or asset.get("url"),
        "size": int(asset.get("size") or 0),
        "digest": (asset.get("digest") or "").lower(),
    }


def download(url, dest, expect_size=0, digest="", timeout=180):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    h = hashlib.sha256()
    got = 0
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with _opener().open(req, timeout=timeout) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            got += len(chunk)
            h.update(chunk)
            f.write(chunk)
    if expect_size and got != expect_size:
        raise RuntimeError("下载大小不对：%d / %d 字节" % (got, expect_size))
    if digest.startswith("sha256:") and h.hexdigest() != digest[7:]:
        raise RuntimeError("下载内容的校验值和发布页不一致")
    return got


def prepare(info):
    dest = os.path.join(update_dir(), "CmdHint-%s.exe" % info["version"])
    download(info["url"], dest, info["size"], info["digest"])
    got = winapi.file_version(dest)
    if got != info["version"]:
        raise RuntimeError("下载的 exe 版本号是「%s」，应为「%s」" % (got or "读不到", info["version"]))
    return dest


UPDATER_NAME = "CmdHint-updater.exe"


def cleanup():
    try:
        names = os.listdir(update_dir())
    except OSError:
        return
    for name in names:
        if name.lower().endswith((".exe", ".ps1")):
            try:
                os.remove(os.path.join(update_dir(), name))
            except OSError:
                pass


def apply_and_restart(new_path):
    upd = update_dir()
    os.makedirs(upd, exist_ok=True)
    helper = os.path.join(upd, UPDATER_NAME)
    shutil.copy2(sys.executable, helper)
    subprocess.Popen([helper, "--apply-update", new_path, sys.executable],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=0x08000000, close_fds=True)


def run_apply(new_path, old_exe):
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            shutil.copy2(new_path, old_exe)
            break
        except OSError:
            time.sleep(0.5)
    time.sleep(1.5)
    try:
        os.startfile(old_exe)
    except OSError:
        pass
    time.sleep(2)
    try:
        os.remove(new_path)
    except OSError:
        pass
    return 0
