# -*- mode: python ; coding: utf-8 -*-
import os
import glob

# Folder that holds this spec file (project root). Works from any folder.
ROOT = SPECPATH

# 1) Loose data files in the project root are bundled automatically.
#    A new logo / image / text / html file only has to be placed here.
_patterns = ["*.png", "*.ico", "*.jpg", "*.jpeg", "*.gif",
             "*.txt", "*.html", "*.md", "*.json"]
# Files that must NOT go inside the exe (user data / build helpers)
_skip = {"requirement.txt", "requirements.txt", "theme_pref.json",
         "DEVELOPER_MANUAL.md"}

datas = []
for _pattern in _patterns:
    for _file in glob.glob(os.path.join(ROOT, _pattern)):
        if os.path.basename(_file) not in _skip:
            datas.append((_file, "."))

# 2) Everything inside these folders (subfolders too) is bundled.
for _folder in ("fonts", "assets"):
    _base = os.path.join(ROOT, _folder)
    if os.path.isdir(_base):
        for _dir, _subdirs, _files in os.walk(_base):
            for _name in _files:
                _target = os.path.relpath(_dir, ROOT)
                datas.append((os.path.join(_dir, _name), _target))


a = Analysis(
    ['login.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NEXO LAN Messenger',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
