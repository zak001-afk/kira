# -*- mode: python ; coding: utf-8 -*-
# KIRA's release build. The app shell (kira_app.py) serves ui/ and shows it
# in a native window, so the HUD files ship as data — not as bundled Python.
from PyInstaller.utils.hooks import collect_all

datas = [('kira_config.json', '.'), ('ui', 'ui')]
binaries = []
hiddenimports = []

# pywebview is the native window. It is optional at runtime (KIRA falls back
# to a browser), so a build without it installed still succeeds.
try:
    tmp_ret = collect_all('webview')
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]
except Exception:
    pass


a = Analysis(
    ['kira_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='KIRA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/kira_app.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KIRA',
)
