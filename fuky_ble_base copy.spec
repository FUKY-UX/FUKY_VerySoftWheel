# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['fuky_ble_base.py'],  # 文件名
    pathex=[],
    binaries=[],
    datas=[
        ('fuky_WinAPI_base.py', '.'),  # 包含同级目录文件
    ],
    hiddenimports=[
        'winrt',
        'winrt.windows.devices.bluetooth',
        'winrt.windows.storage.streams',
        'winrt.windows.devices.enumeration',
        'asyncio.windows_events',  # Windows事件循环支持
        '_cffi_backend',  # C扩展支持
        'concurrent.futures.thread'  # 线程池支持
    ],
    hookspath=['hooks'],  # 指定自定义hook目录
    runtime_hooks=[],
    excludes=['ipykernel', 'spyder'],  # 排除Spyder相关
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='FUKY_BleController',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,  # 调试阶段保留控制台
    icon='app.ico'  # 可选图标文件
)