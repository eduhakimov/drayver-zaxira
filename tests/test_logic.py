import json
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drayver_zaxira import drivers as drv

EN = """Microsoft PnP Utility

Published Name:     oem26.inf
Original Name:      amdfendr.inf
Provider Name:      Advanced Micro Devices, Inc.
Class Name:         System
Class GUID:         {4d36e97d-e325-11ce-bfc1-08002be10318}
Driver Version:     11/22/2023 23.40.0.1
Signer Name:        Microsoft Windows Hardware Compatibility Publisher
Attributes:         Declarative

Published Name:     oem12.inf
Original Name:      nvlddmkm.inf
Provider Name:      NVIDIA
Class Name:         Display
Class GUID:         {4d36e968-e325-11ce-bfc1-08002be10318}
Driver Version:     08/14/2024 32.0.15.6094
Signer Name:        Microsoft Windows Hardware Compatibility Publisher
"""

RU = """Служебная программа PnP Майкрософт

Опубликованное имя:     oem3.inf
Исходное имя:           iastorvd.inf
Имя поставщика:         Intel Corporation
Имя класса:             Контроллеры запоминающих устройств
GUID класса:            {4d36e97b-e325-11ce-bfc1-08002be10318}
Версия драйвера:        07.02.2023 19.5.2.1049
Имя подписавшего:       Microsoft Windows Hardware Compatibility Publisher
"""


def test_parse_english():
    ds = drv.parse_pnputil_enum(EN)
    assert [d.published for d in ds] == ["oem26.inf", "oem12.inf"]
    d = ds[1]
    assert d.original == "nvlddmkm.inf" and d.provider == "NVIDIA" and d.cls == "Display"
    assert d.version == "32.0.15.6094" and d.date == "2024-08-14"
    assert d.signer.startswith("Microsoft Windows Hardware")


def test_parse_localized_by_order():
    ds = drv.parse_pnputil_enum(RU)
    assert len(ds) == 1
    d = ds[0]
    assert d.published == "oem3.inf" and d.original == "iastorvd.inf" and d.provider == "Intel Corporation"
    assert d.version == "19.5.2.1049" and d.date == "2023-02-07"


def test_parse_garbage():
    assert drv.parse_pnputil_enum("") == []
    assert drv.parse_pnputil_enum("Hello: world\n\nfoo") == []


def test_split_version():
    assert drv.split_version("11/22/2023 23.40.0.1") == ("2023-11-22", "23.40.0.1")
    assert drv.split_version("22.11.2023 1.2") == ("2023-11-22", "1.2")
    assert drv.split_version("2023-11-22 1.2") == ("2023-11-22", "1.2")
    assert drv.split_version("weird") == ("", "weird")


def _drivers():
    return [drv.Driver("oem12.inf", "nvlddmkm.inf", "NVIDIA", "Display", version="32.0.15.6094"),
            drv.Driver("oem3.inf", "iastorvd.inf", "Intel", "SCSIAdapter", version="19.5"),
            drv.Driver("oem9.inf", "x.inf", "Microsoft", "Printer", version="1")]


def test_export_plan_by_class():
    plan = drv.export_plan(_drivers()[:2], r"D:\Bk", True)
    folder, args = plan[0]
    assert folder == os.path.join(r"D:\Bk", "Display", "nvlddmkm_32.0.15.6094")
    assert args == ["pnputil.exe", "/export-driver", "oem12.inf", folder]
    flat = drv.export_plan(_drivers()[:1], r"D:\Bk", False)
    assert flat[0][0] == os.path.join(r"D:\Bk", "nvlddmkm_32.0.15.6094")
    assert drv.dism_export_all(r"D:\X") == ["dism.exe", "/online", "/export-driver", r"/destination:D:\X"]


def test_microsoft_flag_and_safe_name():
    assert _drivers()[2].is_microsoft and not _drivers()[0].is_microsoft
    assert drv.safe_name('a<b>:c"d') == "a_b__c_d"


def test_restore_plan_and_bat():
    cmds = drv.restore_plan(r"E:\Bk")
    assert cmds == [["pnputil.exe", "/add-driver", os.path.join(r"E:\Bk", "*.inf"), "/subdirs", "/install"]]
    cmds = drv.restore_plan(r"E:\Bk", [{"folder": "Display/nv_1"}])
    assert cmds[0][2] == os.path.join(r"E:\Bk", "Display", "nv_1", "*.inf")
    bat = drv.to_bat(cmds, [r"E:\Bk\Display"])
    assert "pnputil.exe /add-driver" in bat and 'mkdir "E:\\Bk\\Display"' in bat
    assert drv.cmdline(["a b", "c"]) == '"a b" c'


def test_run_export_with_fake_runner(tmp_path):
    seen = []

    def fake(args):
        seen.append(args)
        Path(args[3], "driver.inf").write_text("[Version]")
        return 0, "Driver package exported successfully."
    res = drv.run_export(_drivers()[:2], str(tmp_path), True, runner=fake)
    assert res["ok"] == 2 and res["failed"] == 0
    assert all(a[1] == "/export-driver" for a in seen)
    m = drv.read_manifest(str(tmp_path))
    assert m["count"] == 2 and m["drivers"][0]["folder"] == "Display/nvlddmkm_32.0.15.6094"
    entries = drv.scan_backup(str(tmp_path))
    assert all(e["exists"] for e in entries)
    z = drv.zip_folder(str(tmp_path), str(tmp_path.parent / "bk.zip"))
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert drv.MANIFEST in names and any(n.endswith("driver.inf") for n in names)


def test_scan_backup_without_manifest(tmp_path):
    (tmp_path / "Net" / "rt").mkdir(parents=True)
    (tmp_path / "Net" / "rt" / "rt640x64.inf").write_text("x")
    e = drv.scan_backup(str(tmp_path))
    assert len(e) == 1 and e[0]["folder"] == "Net/rt" and e[0]["cls"] == "Net"
    assert drv.read_manifest(str(tmp_path)) is None
    (tmp_path / drv.MANIFEST).write_text("{broken")
    assert drv.read_manifest(str(tmp_path)) is None


def test_execute_codes():
    res = drv.execute([["pnputil.exe", "/add-driver", "x"]], runner=lambda a: (259, "no new"))
    assert res[0][1] == 259 and 259 in drv.PNPUTIL_OK

    def boom(a):
        raise OSError("fail")
    res = drv.execute([["x", "y", "z"]], runner=boom)
    assert res[0][1] == -1


def test_real_listing_readonly():
    text = drv.read_pnputil()          # faqat o'qish: /enum-drivers
    ds = drv.parse_pnputil_enum(text)
    assert isinstance(ds, list)
    json.dumps([d.to_dict() for d in ds])
