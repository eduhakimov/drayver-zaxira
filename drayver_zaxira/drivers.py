"""Drayver paketlari: ro'yxat (pnputil /enum-drivers, WMI), eksport va tiklash buyruqlarini tuzish, manifest, zip.

Ro'yxat olish faqat o'qish. Eksport/tiklash buyruqlari alohida tuziladi (build_*), bajarish esa
execute() orqali — testlarda faqat buyruq tuzish tekshiriladi.
"""
import json
import os
import re
import subprocess
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
MANIFEST = "drivers_manifest.json"

_EN_KEYS = {"published name": "published", "original name": "original", "provider name": "provider",
            "class name": "cls", "class guid": "guid", "driver version": "version", "signer name": "signer"}
_ORDER = ["published", "original", "provider", "cls", "guid", "version", "signer"]


@dataclass
class Driver:
    published: str              # oem12.inf
    original: str = ""          # nvlddmkm.inf
    provider: str = ""
    cls: str = ""
    guid: str = ""
    version: str = ""
    date: str = ""              # YYYY-MM-DD
    signer: str = ""
    devices: List[str] = field(default_factory=list)
    checked: bool = False

    @property
    def is_microsoft(self) -> bool:
        return "microsoft" in self.provider.lower()

    def folder_name(self) -> str:
        base = Path(self.original or self.published).stem
        ver = self.version or "0"
        return safe_name(f"{base}_{ver}")

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("checked", None)
        return d


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")
    return s or "_"


def split_version(raw: str) -> Tuple[str, str]:
    """'11/22/2023 23.40.0.1' -> ('2023-11-22', '23.40.0.1'). Mahalliy formatlar (22.11.2023) ham."""
    raw = (raw or "").strip()
    m = re.match(r"(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})\s+(\S+)", raw)
    if not m:
        return "", raw
    a, b, c, ver = m.groups()
    if len(a) == 4:                      # YYYY-MM-DD
        y, mo, d = a, b, c
    elif "." in raw.split()[0]:          # DD.MM.YYYY
        d, mo, y = a, b, c
    else:                                # MM/DD/YYYY
        mo, d, y = a, b, c
    try:
        return datetime(int(y), int(mo), int(d)).strftime("%Y-%m-%d"), ver
    except ValueError:
        return "", ver


def parse_pnputil_enum(text: str) -> List[Driver]:
    """`pnputil /enum-drivers` natijasini tahlil qiladi (ingliz va boshqa tillarda ham: maydon tartibi bo'yicha)."""
    out: List[Driver] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text or "")
    for b in blocks:
        pairs = []
        for line in b.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            pairs.append((k.strip().lower(), v.strip()))
        if not pairs:
            continue
        vals: Dict[str, str] = {}
        for k, v in pairs:
            if k in _EN_KEYS:
                vals[_EN_KEYS[k]] = v
        if "published" not in vals:
            # Tarjima qilingan chiqish: maydonlar tartibi doimiy
            if not re.fullmatch(r"oem\d+\.inf", pairs[0][1], re.I):
                continue
            for i, name in enumerate(_ORDER):
                if i < len(pairs):
                    vals[name] = pairs[i][1]
        if not re.fullmatch(r"oem\d+\.inf", vals.get("published", ""), re.I):
            continue
        date, ver = split_version(vals.get("version", ""))
        out.append(Driver(published=vals["published"].lower(), original=vals.get("original", ""),
                          provider=vals.get("provider", ""), cls=vals.get("cls", ""), guid=vals.get("guid", ""),
                          version=ver, date=date, signer=vals.get("signer", "")))
    return out


def _decode(b: bytes) -> str:
    for enc in ("utf-8", "oem", "mbcs", "cp866"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("latin-1", errors="replace")


def read_pnputil() -> str:
    try:
        r = subprocess.run(["pnputil.exe", "/enum-drivers"], capture_output=True, timeout=120, creationflags=NO_WIN)
        return _decode(r.stdout)
    except Exception:
        return ""


def device_map() -> Dict[str, List[str]]:
    """WMI Win32_PnPSignedDriver: oemXX.inf -> shu drayverdan foydalanuvchi qurilmalar (faqat o'qish)."""
    out: Dict[str, List[str]] = {}
    try:
        import pythoncom
        pythoncom.CoInitialize()
        import wmi
        c = wmi.WMI()
        for d in c.query("SELECT InfName, DeviceName FROM Win32_PnPSignedDriver"):
            inf = (d.InfName or "").lower()
            if inf.startswith("oem") and d.DeviceName:
                out.setdefault(inf, [])
                if d.DeviceName not in out[inf]:
                    out[inf].append(d.DeviceName)
    except Exception:
        pass
    return out


def list_drivers(progress: Callable = None) -> List[Driver]:
    if progress:
        progress(10, "pnputil")
    drivers = parse_pnputil_enum(read_pnputil())
    if progress:
        progress(55, "wmi")
    dm = device_map()
    for d in drivers:
        d.devices = dm.get(d.published.lower(), [])
    drivers.sort(key=lambda d: (d.cls.lower(), d.provider.lower(), d.original.lower()))
    if progress:
        progress(100, "")
    return drivers


# --------------------------------------------------------------------------- eksport
def export_plan(drivers: List[Driver], dest: str, by_class: bool = True) -> List[Tuple[str, List[str]]]:
    """[(papka, buyruq_argumentlari)] — har bir drayver o'z papkasiga (sinf bo'yicha guruhlangan)."""
    plan = []
    for d in drivers:
        parts = [dest]
        if by_class:
            parts.append(safe_name(d.cls or "Other"))
        parts.append(d.folder_name())
        folder = os.path.join(*parts)
        plan.append((folder, ["pnputil.exe", "/export-driver", d.published, folder]))
    return plan


def resolve_target(path: str, computer: str = "") -> str:
    """Zaxira papkasi. Disk ildizi (masalan E: diskning o'zi) tanlansa, ichida alohida papka ochiladi: aks holda ZIP butun
    fleshkani o'z ichiga olardi va "E:.zip" kabi noto'g'ri nom chiqardi."""
    p = os.path.normpath(path.strip())
    drive, rest = os.path.splitdrive(p)
    if rest in ("", "\\", "/", "."):
        p = os.path.join(drive + os.sep, "Drayverlar", safe_name(computer or os.environ.get("COMPUTERNAME", "PC")))
    return p


def zip_path_for(dest: str) -> str:
    d = os.path.normpath(dest)
    return os.path.join(os.path.dirname(d), os.path.basename(d) + ".zip")


def dism_export_all(dest: str) -> List[str]:
    """Barcha uchinchi tomon drayverlarini bitta buyruq bilan eksport qilish (muqobil usul)."""
    return ["dism.exe", "/online", "/export-driver", f"/destination:{dest}"]


def manifest_dict(drivers: List[Driver], dest: str, by_class: bool = True, computer: str = "",
                  windows: str = "") -> dict:
    items = []
    for (folder, _), d in zip(export_plan(drivers, dest, by_class), drivers):
        e = d.to_dict()
        e["folder"] = os.path.relpath(folder, dest).replace("\\", "/")
        items.append(e)
    return {"format": 1, "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "computer": computer or os.environ.get("COMPUTERNAME", ""), "windows": windows,
            "count": len(items), "drivers": items}


def write_manifest(data: dict, dest: str) -> str:
    p = os.path.join(dest, MANIFEST)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return p


def read_manifest(folder: str) -> Optional[dict]:
    p = os.path.join(folder, MANIFEST)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and isinstance(data.get("drivers"), list) else None
    except (OSError, ValueError):
        return None


def scan_backup(folder: str, max_depth: int = 5, limit: int = 2000) -> List[dict]:
    """Zaxira papkasidagi drayverlar: manifest bo'lsa undan, bo'lmasa .inf fayllar bo'yicha."""
    m = read_manifest(folder)
    if m:
        out = []
        for e in m["drivers"]:
            e = dict(e)
            e["exists"] = os.path.isdir(os.path.join(folder, e.get("folder", "")))
            out.append(e)
        return out
    out = []
    base = os.path.abspath(folder).rstrip("\\/").count(os.sep)
    for d, dirs, files in os.walk(folder):
        if os.path.abspath(d).rstrip("\\/").count(os.sep) - base >= max_depth:
            dirs[:] = []
        dirs.sort(key=str.lower)
        infs = sorted(f for f in files if f.lower().endswith(".inf"))
        if not infs:
            continue
        if len(out) >= limit:
            break
        inf = Path(d) / infs[0]
        rel = os.path.relpath(d, folder).replace("\\", "/")
        out.append({"published": "", "original": inf.name, "provider": "", "cls": rel.split("/")[0] if "/" in rel else "",
                    "version": "", "date": "", "folder": rel, "devices": [], "exists": True})
    return out


def restore_plan(folder: str, entries: List[dict] = None) -> List[List[str]]:
    """Tiklash buyruqlari. entries berilmasa — butun papka bitta buyruq bilan."""
    if not entries:
        return [["pnputil.exe", "/add-driver", os.path.join(folder, "*.inf"), "/subdirs", "/install"]]
    cmds = []
    for e in entries:
        sub = os.path.normpath(os.path.join(folder, e.get("folder", "")))
        cmds.append(["pnputil.exe", "/add-driver", os.path.join(sub, "*.inf"), "/subdirs", "/install"])
    return cmds


def cmdline(args: List[str]) -> str:
    return " ".join(f'"{a}"' if (" " in a and not a.startswith('"')) else a for a in args)


def to_bat(cmds: List[List[str]], mkdirs: List[str] = ()) -> str:
    lines = ["@echo off", "chcp 65001 >nul", "rem Drayver zaxiralovchi: administrator sifatida ishga tushiring", ""]
    for d in mkdirs:
        lines.append(f'if not exist "{d}" mkdir "{d}"')
    # .bat ichida "%" o'zgaruvchi belgisi: yo'lda bo'lsa ikkilantiriladi
    lines += [cmdline(c).replace("%", "%%") for c in cmds]
    lines += ["", "pause"]
    return "\r\n".join(lines) + "\r\n"


# --------------------------------------------------------------------------- bajarish
PNPUTIL_OK = {0, 3010, 259}   # 259: yangi drayver yo'q (ERROR_NO_MORE_ITEMS) — xato emas


def execute(cmds: List[List[str]], progress=None, runner: Callable = None,
            on_line: Callable[[str], None] = None) -> List[Tuple[str, int, str]]:
    """Buyruqlarni ketma-ket bajaradi: [(buyruq, kod, chiqish)]. runner(args) -> (kod, matn) testlar uchun."""
    def _run(args):
        r = subprocess.run(args, capture_output=True, creationflags=NO_WIN, timeout=1800)
        return r.returncode, _decode(r.stdout + r.stderr)
    runner = runner or _run
    res = []
    for i, args in enumerate(cmds):
        if progress is not None:
            if getattr(progress, "cancelled", lambda: False)():
                break
            progress(int(i * 100 / max(1, len(cmds))), args[2] if len(args) > 2 else "")
        try:
            code, out = runner(args)
        except Exception as ex:
            code, out = -1, str(ex)
        res.append((cmdline(args), code, out))
        if on_line:
            on_line(f"> {cmdline(args)}\n{out.strip()}\n[{code}]")
    if progress is not None:
        progress(100, "")
    return res


def run_export(drivers: List[Driver], dest: str, by_class=True, progress=None, runner=None, on_line=None,
               windows: str = "") -> dict:
    plan = export_plan(drivers, dest, by_class)
    for folder, _ in plan:
        os.makedirs(folder, exist_ok=True)
    res = execute([a for _, a in plan], progress, runner, on_line)
    ok = [d for d, (_, code, _) in zip(drivers, res) if code in PNPUTIL_OK]
    # Eksport bo'lmagan drayverlar manifestga yozilmaydi, bo'sh papkalari olib tashlanadi
    for (folder, _), d in zip(plan, drivers):
        if d not in ok:
            try:
                os.rmdir(folder)
            except OSError:
                pass
    write_manifest(manifest_dict(ok, dest, by_class, windows=windows), dest)
    return {"results": res, "ok": len(ok), "failed": len(res) - len(ok)}


def zip_folder(folder: str, zip_path: str, progress=None) -> str:
    files = [p for p in Path(folder).rglob("*") if p.is_file()]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for i, f in enumerate(files):
            if progress is not None and i % 20 == 0:
                progress(int(i * 100 / max(1, len(files))), f.name)
            z.write(f, os.path.relpath(f, folder))
    return zip_path


def folder_size(folder: str) -> int:
    return sum(p.stat().st_size for p in Path(folder).rglob("*") if p.is_file())
