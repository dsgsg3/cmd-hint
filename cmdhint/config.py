import json
import os

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CmdHint")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "terminals": [
        "windowsterminal.exe", "openconsole.exe", "conhost.exe", "cmd.exe",
        "powershell.exe", "pwsh.exe", "putty.exe", "kitty.exe", "mobaxterm.exe",
        "xshell.exe", "xshell7.exe", "securecrt.exe", "mintty.exe", "conemu64.exe",
        "conemu.exe", "wezterm-gui.exe", "alacritty.exe", "tabby.exe",
        "termius.exe", "finalshell.exe", "bash.exe", "wsl.exe",
    ],
    "scope": "all",
    "exclude": [
        "keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe",
        "lastpass.exe", "mstsc.exe", "logonui.exe", "consent.exe",
    ],
    "min_chars": 1,
    "max_items": 5,
    "api_base_url": "",
    "api_key": "",
    "api_model": "",
    "ai_cmd": ["kimi", "-p", "{prompt}", "--output-format", "text"],
    "ai_prompt": (
        "你是资深 Linux 运维工程师。用户想做的事：{query}\n"
        "（这段话可能是中文、英文、拼音全拼，或拼音首字母缩写，如 neicun、nczy；请先还原它想表达的意思，再给命令。）\n"
        "给出 5 条可用的命令，按与需求的贴合程度从高到低排列，第 1 条必须是最贴合的。\n"
        "每条严格两行：\n"
        "COMMAND: <命令。用户需求里已给出的端口、路径、名称、数值等具体值，必须原样写进命令；只有没给出的才用 <尖括号> 占位>\n"
        "NOTE: <一句中文说明>\n"
        "共 5 组，不要编号，不要代码块，不要调用任何工具，不要输出其他内容。"
    ),
    "ask_prompt": (
        "你是资深 Linux/Windows 运维工程师，请全程用简体中文回答。用户的问题：{query}\n"
        "（问题可能是中文、英文或拼音，先理解它的意思。）\n"
        "情况一：用户想完成某件事或需要某条命令。给出 5 条可用命令，按与需求的贴合程度从高到低排列，第 1 条必须最贴合。每条严格两行：\n"
        "COMMAND: <命令。用户已给出的端口、路径、名称、数值等具体值必须原样写进去；没给出的才用 <尖括号> 占位>\n"
        "NOTE: <一句中文说明>\n"
        "情况二：用户问的是概念、原理或排查思路，不需要命令。只输出一段：\n"
        "ANSWER: <中文回答，不超过 120 字，要点式，用分号隔开，不要换行>\n"
        "不要代码块，不要调用任何工具，不要输出其他内容。"
    ),
    "explain_prompt": (
        "你是资深 Linux 运维工程师。请用中文讲解这条命令：{command}\n"
        "严格按下面格式输出，不要代码块，不要多余内容：\n"
        "SUMMARY: <一句话说明它做什么>\n"
        "PART: <命令中的一段> = <这段的作用>\n"
        "（每个参数或管道段一行，最多 8 行）\n"
        "RISK: <有没有危险、在哪类环境容易出问题；没有就写 无>\n"
    ),
    "error_prompt": (
        "你是资深 Linux 运维工程师。下面是一段报错信息：\n---\n{error}\n---\n"
        "先判断最可能的原因，再给出修复命令，按可能性从高到低最多 5 条。\n"
        "严格按下面格式输出，不要代码块，不要调用任何工具：\n"
        "CAUSE: <一到两句中文，说明最可能的原因>\n"
        "COMMAND: <命令。报错里出现的路径、主机、服务名等要原样用上；其它才用 <尖括号> 占位>\n"
        "NOTE: <一句中文说明>\n"
    ),
    "ai_timeout": 60,
    "custom_commands": [],
}


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    cfg["terminals"] = [t.lower() for t in cfg["terminals"]]
    cfg["exclude"] = [t.lower() for t in cfg["exclude"]]
    return cfg


def save_defaults_if_missing():
    if os.path.exists(CONFIG_PATH):
        return
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
