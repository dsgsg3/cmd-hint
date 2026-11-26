import os
import sys

from version import VERSION

NAME = "命令提示"

TEMPLATE = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=%(vers)s,
    prodvers=%(vers)s,
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404b0', [
        StringStruct('FileDescription', '%(name)s'),
        StringStruct('FileVersion', '%(version)s'),
        StringStruct('InternalName', 'CmdHint'),
        StringStruct('OriginalFilename', '%(name)s.exe'),
        StringStruct('ProductName', '%(name)s'),
        StringStruct('ProductVersion', '%(version)s')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def text(version=VERSION):
    return TEMPLATE % {"vers": tuple(int(p) for p in version.split(".")),
                       "name": NAME, "version": version}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "version_info.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text())
    print(path)


if __name__ == "__main__":
    main()
