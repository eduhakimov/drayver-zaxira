"""Zaxiralash va tiklash ssenariylari. pnputil HECH QACHON haqiqatda chaqirilmaydi:
subprocess.run soxta funksiya bilan almashtiriladi va u qanday buyruq berilganini yozib boradi.
"""
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from drayver_zaxira import drivers as drv


def _drivers():
    return [drv.Driver("oem12.inf", "nvlddmkm.inf", "NVIDIA", "Display", version="32.0.15.6094", checked=True),
            drv.Driver("oem3.inf", "iastorvd.inf", "Intel", "SCSIAdapter", version="19.5", checked=True),
            drv.Driver("oem7.inf", "broken.inf", "Realtek", "Net", version="1.0", checked=True)]


class FakePnputil:
    """pnputil o'rniga: eksportda .inf yaratadi, oem7 uchun xato qaytaradi."""

    def __init__(self):
        self.calls = []

    def __call__(self, args, **kw):
        assert args[0] == "pnputil.exe", args
        self.calls.append(list(args))
        code = 0
        if args[1] == "/export-driver":
            if args[2] == "oem7.inf":
                code = 1
            else:
                Path(args[3], args[2].replace("oem", "drv")).write_text("[Version]")
        return subprocess.CompletedProcess(args, code, b"ok", b"")


def test_resolve_target_and_zip_name():
    assert drv.resolve_target("E:\\", "ASUS-PC") == os.path.join("E:\\", "Drayverlar", "ASUS-PC")
    assert drv.resolve_target("E:", "ASUS-PC") == os.path.join("E:\\", "Drayverlar", "ASUS-PC")
    assert drv.resolve_target("D:\\Zaxira\\PC\\", "x") == "D:\\Zaxira\\PC"
    assert drv.zip_path_for("D:\\Zaxira\\PC\\") == "D:\\Zaxira\\PC.zip"


def test_bat_escapes_percent(tmp_path):
    bat = drv.to_bat([["pnputil.exe", "/add-driver", "D:\\100% zaxira\\*.inf", "/subdirs", "/install"]])
    assert '"D:\\100%% zaxira\\*.inf"' in bat


def test_failed_export_not_in_manifest(tmp_path, monkeypatch):
    fake = FakePnputil()
    monkeypatch.setattr(drv.subprocess, "run", fake)
    dest = tmp_path / "Zaxira o'zbek" / "Компьютер"
    res = drv.run_export(_drivers(), str(dest))
    assert res["ok"] == 2 and res["failed"] == 1
    assert fake.calls[0] == ["pnputil.exe", "/export-driver", "oem12.inf",
                             str(dest / "Display" / "nvlddmkm_32.0.15.6094")]
    m = drv.read_manifest(str(dest))
    assert [e["published"] for e in m["drivers"]] == ["oem12.inf", "oem3.inf"]
    assert not (dest / "Net").exists() or not any((dest / "Net").rglob("*"))
    assert all(e["exists"] for e in drv.scan_backup(str(dest)))


def _app():
    from PySide6.QtWidgets import QApplication
    from uzkit import app as appmod, i18n
    from uzkit.settings import Settings
    appmod.META = appmod.load_meta()
    appmod.SETTINGS = Settings(appmod.META["slug"] + "_test")
    QApplication.instance() or QApplication([])
    i18n.set_language("ru")


def _wait(cond, timeout=10.0):
    from PySide6.QtWidgets import QApplication
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_backup_then_restore_through_ui(tmp_path, monkeypatch):
    _app()
    from drayver_zaxira import window as W
    fake = FakePnputil()
    monkeypatch.setattr(drv.subprocess, "run", fake)
    monkeypatch.setattr(drv, "list_drivers", lambda progress=None: _drivers())
    for name in ("is_admin", "ask"):
        monkeypatch.setattr(W, name, lambda *a, **k: True)
    monkeypatch.setattr(W, "info", lambda *a, **k: None)
    monkeypatch.setattr(W, "open_path", lambda p: None)
    win = W.MainWindow()
    win.load()
    assert _wait(lambda: win.job is None and len(win.backup.items) == 3)
    dest = tmp_path / "Zaxira" / "PC 1"
    win.backup.target.set_path(str(dest))
    win.backup.zip.setChecked(True)
    win.backup._backup()
    win.backup._backup()                         # ikkinchi bosish: ish tugamaguncha yangisi boshlanmaydi
    assert _wait(lambda: win.job is None and (tmp_path / "Zaxira" / "PC 1.zip").exists())
    assert sum(1 for c in fake.calls if c[1] == "/export-driver") == 3
    with zipfile.ZipFile(tmp_path / "Zaxira" / "PC 1.zip") as z:
        assert drv.MANIFEST in z.namelist()

    fake.calls.clear()
    win.restore.folder.set_path(str(dest))
    win.restore.load()
    assert len(win.restore.entries) == 2
    win.restore._restore()
    assert _wait(lambda: win.job is None and len(fake.calls) == 2)
    assert fake.calls[0] == ["pnputil.exe", "/add-driver",
                             os.path.join(str(dest), "Display", "nvlddmkm_32.0.15.6094", "*.inf"),
                             "/subdirs", "/install"]
    win.close()
