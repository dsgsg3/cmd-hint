# 命令提示工具 · 项目说明

给后续维护者（包括 AI 助手）看的说明。改动前先读完，尤其是「坑」那一节。这里的描述如果和代码不一致，以代码为准，并顺手改这份说明。

## 项目是什么

Windows 上的本地小工具，面向记不住命令的运维人员。同一个文件夹里有两个独立的程序：

| 文件 | 作用 |
|---|---|
| `index.html` `app.js` `data.js` `styles.css` `app.py` | **运维命令速查**：本地网页版命令手册。`app.py` 在 `127.0.0.1:8765` 起本地服务（被占用则顺延）并用 pywebview 开窗口；收藏和自定义命令存在浏览器 localStorage（`%LOCALAPPDATA%\OpsCmd\webview`） |
| `cmdhint/` | **命令提示**：常驻托盘，全局监听键盘，在任意窗口敲字时于提示条里给出命令。目前主要在维护的是它 |
| `icon.ico` | 两个程序共用的图标 |
| `一键打包.cmd` | 双击就打包并启动新版，内部调用 `cmdhint/build.py` |
| `dist/` | 打包产物，已被 `.gitignore` 排除 |

`cmdhint/` 内部：

| 文件 | 作用 |
|---|---|
| `main.py` | 入口。`App` 类持有全部状态，`handle()` 分发事件队列，`render()` 决定提示条显示什么 |
| `engine.py` | 全局键盘钩子（`keyboard` 库，`suppress=True`）。维护输入缓冲 `buf`，把事件放进队列；填参时用 `_fill_key` 拦键 |
| `bar.py` | tkinter 提示条。无边框、置顶、不抢焦点；按像素宽度裁剪文字；提问模式临时接管焦点 |
| `matcher.py` | 命令匹配。加载 `commands.json` 和 `commands_extra.txt`，启动时预计算拼音 |
| `util.py` | 占位符识别、命令拼装、危险命令识别 `is_dangerous`、开机自启、提示条位置存取、文字裁剪 |
| `winapi.py` | ctypes 封装的 Win32 调用：前台窗口、按键转字符、SendInput、窗口样式、输入法状态 |
| `ai.py` | AI 调用：问命令、提问模式、讲解、报错分析；走云端 API 或本机 `kimi` 命令 |
| `config.py` | 默认配置，以及 `%APPDATA%\CmdHint\config.json` 的读取 |
| `version.py` | 版本号，全项目唯一的一处 |
| `make_version_info.py` | 由 `version.py` 生成 exe 的版本信息 `version_info.txt`。`build.py` 会调用它；单独运行会在同目录生成文件（那个文件不进仓库） |
| `build.py` | 一键打包：检查依赖、结束旧进程、打包、核对版本号、保留上一版、启动并确认提示条出现，失败自动回滚 |
| `commands.json` | 第一阶段从 `data.js` 导出的 228 条命令。和 `data.js` 各自维护，没有自动同步 |
| `commands_extra.txt` | 后来扩充的约 2300 条命令，一行一条 |

## 和用户协作的方式

- 用户是运维，不是开发。用中文、说人话，少用术语。
- 用户经常一边用电脑一边让我测试。不要跑会抢前台焦点、往窗口里打字的测试，除非每次按键前都确认前台是测试窗口，不是就中止。
- 只关闭自己开的测试窗口（标题以 `CHTEST` 开头）。不要按进程名结束终端（`WindowsTerminal.exe`、`cmd.exe`），会关掉用户自己的窗口。
- `dist\命令提示.exe` 通常正在运行。重新打包用 `python cmdhint/build.py`（或双击 `一键打包.cmd`），它会自己结束旧进程；不要手敲 PyInstaller 命令。
- 测试不要动用户的剪贴板。必须用时先备份、测完恢复。
- 不要把 API Key 写进源码、提交或日志。Key 只在 `%APPDATA%\CmdHint\config.json`。

## 运行与配置

源码运行（在 `cmdhint/` 下）：

```
python main.py
```

源码版正常运行时终端里没有任何输出，出错会直接打印然后退出，排查问题要把输出重定向到文件。打包成的 exe 是无窗口程序，报错完全看不到。重复启动会被单实例互斥量拦住，第二个直接退出。

运行期文件都不在仓库里：

- `%APPDATA%\CmdHint\config.json`：用户配置，首次启动写入默认值。主要项：
  - `api_base_url` / `api_key` / `api_model`：云端 AI（OpenAI 兼容接口）。三项齐全才用云端，否则退回 `ai_cmd`（默认 `kimi -p`）。
  - `ai_prompt` `ask_prompt` `explain_prompt` `error_prompt`：四类提示词。
  - `scope`：`"all"` 时所有窗口都提示；否则只认 `terminals` 列表里的程序。
  - `exclude`：从不记录按键的程序名。
  - `min_chars` `max_items` `ai_timeout` `custom_commands` `update_mode` `update_proxy`。`update_mode` 三档：`download`（默认，下载并提示）、`auto`（下载后自动重启）、`off`（不检查）。
- `%APPDATA%\CmdHint\state.json`：提示条的位置和大小（`x` `y` `w` `rows`），用户拖动后自动保存。不要随手删，那是用户调好的位置。
- `%APPDATA%\CmdHint\commands_user.txt`：用户自己的命令库，首次启动用模板生成（全部是注释）。主程序每秒比对它的修改时间，变了就在后台线程重建 Matcher（约 1 秒）；重建期间提示条沿用旧数据，完成后自动刷新当前搜索。同一条命令以这个文件为准，覆盖内置的。

快捷键都是 Ctrl+Alt 加一个键，由 `engine.py` 拦截：

| 键 | 作用 |
|---|---|
| `1`~`9` | 插入第 N 条。处于「讲解待选」时改为讲解该条 |
| `A` | 把终端里已经敲的内容发给 AI |
| `Q` | 提问模式：提示条变成输入框，可以输中文。Enter 发送，Esc 取消 |
| `E` | 读剪贴板里的报错，AI 给原因和修复命令 |
| `X` | 讲解。有待选命令时进入「选一条」，否则讲解终端里已敲的整条命令 |
| `P` | 暂停或恢复 |

托盘菜单：暂停、开机自启、打开配置文件、打开命令文件、退出。

## 打包

一键打包：双击项目根目录的 `一键打包.cmd`，或在 `cmdhint/` 下运行 `python build.py`。

脚本依次做这些事，任何一步失败都不会留下坏版本：

1. 检查依赖（PyInstaller、keyboard、pystray、PIL、pypinyin）和数据文件是否齐全。
2. 结束正在运行的 `命令提示.exe`。
3. 在临时目录里打包，核对新 exe 的文件版本号等于 `version.py` 里的版本。
4. 把现在的 exe 存为 `dist\命令提示.上一版.exe`，再用新版替换。
5. 启动新版，确认提示条真的出现（找到属于新进程的 `TkTopLevel` 窗口）。没出现就换回上一版并重新启动，退出码为 1，并在 `%TEMP%\命令提示-打包失败.log` 留下打包日志。

- `python build.py --check` 只检查环境和文件，不动任何东西，也不结束进程。
- `python build.py --no-start` 打包并替换，但不启动。
- 脚本内部调用的 PyInstaller 参数：`--onefile --windowed --noconfirm --name "命令提示" --icon <根目录 icon.ico> --version-file <临时目录>\version_info.txt --add-data <绝对路径>;. ×3 --hidden-import pystray._win32 --hidden-import pypinyin --collect-data pypinyin --paths <cmdhint> --distpath/--workpath/--specpath <临时目录> <cmdhint>\main.py`。路径都写成绝对路径，所以 `--specpath` 不再破坏相对路径，这是手敲命令时踩过的坑。
- 新增数据文件时，要同时加进 `build.py` 的 `--add-data` 列表，并确认 `matcher.resource_path()` 能读到。
- `--collect-data pypinyin` 必须有，否则 exe 里没有拼音词典。
- 版本号只改 `version.py`。`version_info.txt` 由脚本在临时目录生成，不要手改，也不要提交。
- 源码和打包都从项目根目录取 `icon.ico`，不需要再往 `cmdhint/` 里拷贝。

环境：Python 3.12.10；`keyboard 0.13.5`、`pystray 0.19.5`、`pypinyin 0.55.0`、`Pillow 12.3.0`、`pyinstaller 6.22.3`；`pywebview 6.2.1` 只有第一阶段的 `app.py` 用到。`psutil` 装了，但代码没有用到。

`dist\运维命令速查.exe` 是第一阶段用 `app.py` 打的，之后没再打过，当时的打包命令没有记录。

## 版本号

四段式 `主.次.中.小`，当前是 `1.0.1.4`。全项目只在 `cmdhint/version.py` 里写版本号，提示条标题、托盘提示和 exe 的文件属性都从它来。

历史：`1.0.0.0` 第一个版本；`1.0.0.1` 加了一键打包脚本；`1.0.1.0` 命令库可外置（`%APPDATA%\CmdHint\commands_user.txt`，保存即生效）；`1.0.1.2` 加自动更新；`1.0.1.3` 修自动更新的后台启动方式（`DETACHED_PROCESS` 启动的 PowerShell 会立刻退出）；`1.0.1.4` 修替换后立刻启动导致的 `Failed to load Python DLL`（改为等 5 秒再启动，失败重试）。

- **小版本**：第 4 段加 1，范围 1 到 5。修 bug、做小调整，用法不变。
- **中版本**：第 3 段加 1、第 4 段归 0，范围 1 到 5。新增功能或用法有变化，比如新快捷键、新模式、命令库大扩充。要不要加由开发者判断。
- **大版本**：第 1 段加 1，其余归 0。整体方式的大改。
- 第 2 段目前不用，保持 0。
- 小版本到 5 之后还有小改动，进位到中版本；中版本到 5 之后，进位到大版本。进位规则是按用户的意思理解的，用户没有逐字确认过。

升版本的步骤：

1. 改 `version.py`。
2. 运行一键打包（`python build.py`）。它会核对新 exe 的版本号、保留上一版、并确认新版能启动。
3. 提交，提交说明里写版本号，并打标签 `v版本号`，例如 `v1.0.0.1`。
4. 发 Release。附件名要用纯英文：文件名带中文会被 GitHub 改成 `default.exe`（踩过）。先复制一份：

   ```
   cp "dist/命令提示.exe" /tmp/CmdHint-<版本>.exe
   gh release create v<版本> /tmp/CmdHint-<版本>.exe --title "命令提示 <版本>" --notes-file <说明文件> --latest
   ```

   exe 不进仓库，作为附件上传。发布说明里要写 SHA256、首次运行会被 Windows 提示「未知发布者」、以及已知限制。上传走 `api.github.com`，这台机器能直连；改说明用 `gh release edit v<版本> --notes-file <文件>`。

## Git 与推送

- 远程是 `https://github.com/dsgsg3/cmd-hint`（2026-11-26 从 `dsgsg3/-` 改名而来，旧地址会自动跳转），**公开**仓库，分支 `main`。提交者身份只在本仓库里设置：`dsgsg3`，用 GitHub 的匿名邮箱。
- `dist/`、`build/`、`*.spec`、`__pycache__/` 已忽略。exe 不进仓库，用户需要时再传 GitHub Release。
- 这台电脑直连不上 `github.com:443`，但 `api.github.com` 是通的。推送要走系统代理，代理地址查注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings` 的 `ProxyServer`。写这份说明时是 `127.0.0.1:17891`（Clash Verge），端口可能会变。
- 凭据用 `gh` 已登录的账号。代理和凭据都只在命令里临时指定，没有改全局 git 配置：

```
git -c http.proxy=http://127.0.0.1:17891 -c credential.helper= -c "credential.helper=!gh auth git-credential" push
```

- 所以直接敲 `git push` 会失败，这是预期的。不要强推。

## 架构要点

- **线程**：键盘钩子在独立线程，只做轻量判断，然后把事件放进 `queue`。tkinter 主线程每 25 毫秒 `pump()` 取出来处理。任何 tkinter 调用只能在主线程。插入命令的 `inject()` 在工作线程里调 SendInput，期间把 `engine.injecting` 设为 True，让钩子忽略自己发出的按键。
- **提示条窗口**：用 Win32 `ShowWindow` 显示，不走 tkinter 的 deiconify。扩展样式带 `WS_EX_NOACTIVATE`，所以点它不会抢走终端焦点。`winfo_viewable()` 对这种窗口不可靠，用 `bar.shown` 标志判断。
- **焦点切换**：提问模式会临时去掉 NOACTIVATE 并抢焦点，否则中文输入法的汉字进不来。结束后焦点还回原窗口，引擎会把它当成「切换了窗口」，触发 `on_ctx()` 清空显示。所以有两层保护：`ctx_hold`（提问结束后 2.5 秒内忽略这次变化）和「AI 等待期间不清空」。`check_ask_focus` 在 250 毫秒后检查，没抢到焦点就取消提问，避免把字打进终端。
- **拦键**：`engine._block(scan_code)` 返回 False 吞掉按键，并记下 scan code，用来吞掉对应的抬起事件。
- **缓冲**：`engine.buf` 记的是「用户敲了什么」，不是终端里的真实内容。方向键、Tab、粘贴、Enter、Esc 会清空或截断它。`comp` 是中文输入法里还没上屏的拼音字母数，这期间按空格或数字是选字，缓冲要清空。
- **占位符**：`{{容器}}` 是要用户填的参数。`{{.Names}}`、`{{json .}}` 这类是 Go 模板，原样保留，判断在 `util._is_param`。
- **危险命令**：`util.is_dangerous()` 是正则启发式，整体不区分大小写，只有 `git branch -D` 区分大小写。它只是尽力而为，不是保证。
- **AI**：全部在工作线程。云端请求带 `"thinking": {"type": "disabled"}` 关闭推理，否则一次要 30 到 55 秒；接口不认这个参数（返回 400 或 422）时，自动重发一次不带它的请求。结果按提示词缓存。
- **拼音**：`matcher` 启动时用 pypinyin 给每条命令的说明算全拼和首字母，2500 多条约 1 秒。首字母缩写 2 个字母只认开头，3 个字母起可以匹配中间。
- **自动更新**：`update.py`。`GET /repos/dsgsg3/cmd-hint/releases/latest`（走 `urllib` 的 `ProxyHandler()`，默认读系统代理；`update_proxy` 可覆盖）→ 取 tag 和名字形如 `CmdHint-x.y.z.w.exe` 的附件 → 比版本号 → 下载到 `%APPDATA%\CmdHint\update\`，依次校验附件大小、发布页的 `digest`（sha256）和下载文件自带的 FileVersion。替换自己不能在本进程做：写一个 UTF-8 BOM 的 `install.ps1`（PS 5.1 读带 BOM 才认 UTF-8，路径含中文），用 `CREATE_NO_WINDOW` 启动，等 exe 解锁（最多 60 次 × 0.7 秒）、覆盖、`Start-Process` 重启、自删；替换前主程序会先测 exe 目录是否可写。启动 20 秒后查一次，之后每 6 小时一次。**坑**：用 `DETACHED_PROCESS`（0x8）启动的 PowerShell 会立刻退出，什么都做不了（实测过，三种方式对比只有 `CREATE_NO_WINDOW` 和 `cmd start /b` 能活）。另一个坑：替换完立刻启动，新进程解压时会报 `Failed to load Python DLL`（杀毒扫描新文件、旧进程临时目录清理撞车），所以脚本里先等 5 秒，启动后 6 秒内退出就重试，最多 3 次。
- **命令文件**：三层来源，后面的覆盖前面的同名命令 —— `commands.json`（第一阶段导出）、`commands_extra.txt`（内置扩充）、`%APPDATA%\CmdHint\commands_user.txt`（用户自己的）。格式一行一条 `分类¦命令¦说明¦标签(逗号分隔)¦标志`，`d` 危险、`h` 常用，新分类用 `@cat¦id¦名称` 声明；分类标签也是用户文件优先。主程序每秒看用户文件的 mtime，变了就起线程重建 Matcher（含拼音预计算），完成后经队列把新对象交回主线程替换。

## 怎么测试

仓库里没有自动化测试。以往每次改动都是临时写脚本、测完删除。可以复用的三种做法：

1. **假事件单测引擎**：实例化 `Engine`，把 `winapi.foreground`、`process_name`、`key_down`、`char_for_scan` 换成假函数，用带 `name`、`scan_code`、`event_type` 属性的假对象调 `engine.on_event()`，检查返回值（False 表示按键被拦下）和队列里的事件。
2. **不碰键盘的测试台**：`import main as M`，`app = M.App()`。把 `app.engine.start` 和 `app.start_tray` 换成空函数（不装钩子、不出托盘），把 `app.inject` 换成只记录参数的函数（不真打字）。然后用 `app.handle(("buf", "...", hwnd))`、`app.pick(0)` 这类调用直接驱动，用 `app.root.update()` 处理 tkinter 事件，对提示条窗口截图核对显示。
3. **真实键盘**：必须从另一个进程注入按键。同一个进程里用 `keyboard.write` 或 `press_and_release` 注入的事件，会被钩子当成自己的回放直接跳过，看起来像「钩子没反应」。

跑测试台之前要先结束正在运行的实例，否则会出现两个提示条。按进程名结束 `python.exe` 会误伤用户自己的 python 进程，按命令行或 PID 结束更稳妥。

改 `build.py` 之后，先跑 `python build.py --check`。要验证失败路径而不影响正在运行的程序：把 `cmdhint/` 复制到临时目录，在副本的 `dist/` 里放两个假的 exe 文件，再打桩 `stop_running`（空函数）、`os.startfile`（只记录）、`bar_visible`（返回 False），然后调副本里的 `main()`。指标是：退出码为 1、原来的版本被恢复、上一版没有被覆盖。

## 坑（都踩过）

- **写文件**：用 Write 分段写已有文件时，第二段起必须带 `mode=append`。漏了会把整个文件覆盖成只剩那一段，`main.py` 和 `bar.py` 各中过一次。改已有文件优先用 Edit。
- **并行调用**：不要在同一次并行调用里一边写文件、一边运行依赖这个文件的命令。命令可能先执行，报文件不存在。
- **heredoc**：在 Bash 里用 `cat <<EOF` 写含 `EOF` 字样或 `\n` 转义的内容，会被截断或吃掉转义。内容用 Write 工具写。
- **从 Bash 启动 exe**：用 `start "" "命令提示.exe"` 启动的 exe 会占住命令的输出通道，命令一直挂到 exe 退出，挂过 94 分钟。验证时用 PowerShell 的 `Start-Process` 启动，它会立即返回。
- **Alt+数字收不到**：这台机器上 `Alt+字母` 和 `Alt+数字` 的按下事件到不了钩子，原因没查明。所以所有快捷键都用 Ctrl+Alt。
- **前台被抢**：用户的其他程序（比如 putty）会抢走前台。测试脚本里每次按键前都要检查前台窗口。
- **exe 要单独验**：源码版通过不代表 exe 通过，尤其是 `--add-data` 的数据文件和 hidden import。
- **截图裁剪**：提示条的位置由用户决定，存在 `state.json` 里。不要按左上角裁剪，先取窗口矩形。

## 已知限制与未完成项

- exe 里的提问模式（`Ctrl+Alt+Q`）没有端到端验证过，只验证了源码版。
- 缓冲会和终端里的真实内容对不上（方向键、Tab、粘贴之后）。这是设计上的先天限制，看不到终端那一行。
- 管理员权限的窗口，要用管理员身份启动本程序才收得到按键。
- 只在微软拼音下测过，搜狗等其它输入法没验证。
- 还没做：测试入库（把上面三种测试写进仓库）。
