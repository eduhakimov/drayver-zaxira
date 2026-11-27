"""Asosiy oyna: asboblar paneli + ish maydoni (zaxiralash, tiklash, jurnal)."""
import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QProgressBar,
                               QPushButton, QSplitter, QStackedWidget, QTabBar, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from uzkit import app as appmod
from uzkit.i18n import register, tr
from uzkit.paths import documents_dir, resource
from uzkit.widgets import (PathPicker, Worker, ask, error, info, is_admin, open_path, primary_button, run_worker,
                           warn)
from uzkit.window import BaseMainWindow

from . import drivers as drv
from .adminbar import do_relaunch
from .strings import STRINGS
from .ui import dot_icon, svg_icon

register(STRINGS)

DEMO = "--screenshot" in sys.argv
AUTO = not DEMO and "pytest" not in sys.modules


def demo_drivers():
    rows = [
        ("oem12.inf", "nvlddmkm.inf", "NVIDIA", "Display", "32.0.15.6094", "2024-08-14", ["NVIDIA GeForce RTX 3060"]),
        ("oem8.inf", "iigd_dch.inf", "Intel Corporation", "Display", "31.0.101.4502", "2023-06-20", ["Intel(R) UHD Graphics 630"]),
        ("oem31.inf", "hdxrt.inf", "Realtek Semiconductor Corp.", "MEDIA", "6.0.9600.1", "2024-02-02", ["Realtek High Definition Audio"]),
        ("oem40.inf", "nvhda.inf", "NVIDIA Corporation", "MEDIA", "1.4.2.6", "2024-06-11", ["NVIDIA High Definition Audio"]),
        ("oem21.inf", "rt640x64.inf", "Realtek", "Net", "10.68.815.2023", "2023-08-15", ["Realtek PCIe GbE Family Controller"]),
        ("oem44.inf", "netwtw08.inf", "Intel", "Net", "23.60.1.2", "2024-05-21", ["Intel(R) Wi-Fi 6 AX201 160MHz"]),
        ("oem17.inf", "ibtusb.inf", "Intel Corporation", "Bluetooth", "23.60.5.10", "2024-05-23", ["Intel(R) Wireless Bluetooth(R)"]),
        ("oem5.inf", "heci.inf", "Intel", "System", "2406.5.5.0", "2024-03-08", ["Intel(R) Management Engine Interface #1"]),
        ("oem26.inf", "amdfendr.inf", "Advanced Micro Devices, Inc.", "System", "23.40.0.1", "2023-11-22", []),
        ("oem3.inf", "iastorvd.inf", "Intel Corporation", "SCSIAdapter", "19.5.2.1049", "2023-02-07", ["Intel RST VMD Controller 9A0B"]),
        ("oem52.inf", "synpd.inf", "Synaptics", "Mouse", "19.5.35.1", "2023-04-04", ["Synaptics Pointing Device"]),
        ("oem60.inf", "rtsuvc.inf", "Realtek Semiconductor Corp.", "Camera", "10.0.22000.20328", "2023-10-12", ["Integrated Camera"]),
        ("oem71.inf", "prnhpcl1.inf", "Microsoft", "Printer", "10.0.22621.1", "2006-06-21", []),
        ("oem9.inf", "cardreader.inf", "Realtek Semiconductor Corp.", "SDHost", "10.0.22000.21355", "2022-09-02", ["Realtek PCIE CardReader"]),
    ]
    out = []
    for i, (pub, orig, prov, cls, ver, date, devs) in enumerate(rows):
        out.append(drv.Driver(pub, orig, prov, cls, "", ver, date, "Microsoft Windows Hardware Compatibility Publisher",
                              devs, checked=i not in (8, 12)))
    return out


def _table(cols, stretch) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    t.setWordWrap(False)
    t.setShowGrid(False)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.Interactive)
    h.setSectionResizeMode(stretch, QHeaderView.Stretch)
    h.setHighlightSections(False)
    t.verticalHeader().setDefaultSectionSize(30)
    return t


def _it(text, checkable=False, checked=False) -> QTableWidgetItem:
    it = QTableWidgetItem(text or "")
    flags = it.flags() & ~Qt.ItemIsEditable
    if checkable:
        flags |= Qt.ItemIsUserCheckable
        it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    it.setFlags(flags)
    return it


class CommandsDialog(QDialog):
    def __init__(self, parent, cmds, mkdirs=()):
        super().__init__(parent)
        self.setWindowTitle(tr("commands_title"))
        self.resize(820, 420)
        self.cmds, self.mkdirs = cmds, mkdirs
        l = QVBoxLayout(self)
        t = QPlainTextEdit("\n".join(drv.cmdline(c) for c in cmds))
        t.setReadOnly(True)
        t.setLineWrapMode(QPlainTextEdit.NoWrap)
        t.setObjectName("Mono")
        l.addWidget(t)
        row = QHBoxLayout()
        row.addStretch(1)
        b1 = QPushButton(tr("copy"))
        b2 = QPushButton(tr("save_bat"))
        b3 = QPushButton(tr("close"))
        for b in (b1, b2, b3):
            row.addWidget(b)
        l.addLayout(row)
        b1.clicked.connect(lambda: QGuiApplication.clipboard().setText(t.toPlainText()))
        b2.clicked.connect(self._bat)
        b3.clicked.connect(self.accept)

    def _bat(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("save_bat"), str(documents_dir() / "drayverlar.bat"), "Batch (*.bat)")
        if p:
            Path(p).write_text(drv.to_bat(self.cmds, self.mkdirs), encoding="utf-8", newline="")


class SidePanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("SidePanel")
        self.setMinimumWidth(270)
        self.setMaximumWidth(330)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(10)

    def title(self, text):
        l = QLabel(text)
        l.setObjectName("PanelTitle")
        self.lay.addWidget(l)
        return l

    def sep(self):
        f = QFrame()
        f.setObjectName("Sep")
        f.setFixedHeight(1)
        self.lay.addWidget(f)


class _Bridge(QObject):
    line = Signal(str)


# =========================================================================== Zaxiralash
class BackupPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.items = []
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(18, 14, 14, 14)
        lv.setSpacing(10)
        fr = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("filter_ph"))
        self.search.setClearButtonEnabled(True)
        fr.addWidget(self.search, 1)
        self.cls = QComboBox()
        self.cls.setMinimumWidth(170)
        fr.addWidget(self.cls)
        self.hide_ms = QCheckBox(tr("hide_ms"))
        self.hide_ms.setChecked(True)
        fr.addWidget(self.hide_ms)
        lv.addLayout(fr)
        self.table = _table(["", tr("col_provider"), tr("col_class"), tr("col_inf"), tr("col_version"), tr("col_date"),
                             tr("col_devices")], 1)
        for i, w in enumerate([34, 0, 100, 130, 105, 84, 190]):
            if not w:
                continue
            self.table.setColumnWidth(i, w)
        lv.addWidget(self.table, 1)
        br = QHBoxLayout()
        self.count = QLabel("")
        self.count.setObjectName("Muted")
        br.addWidget(self.count, 1)
        b_all = QPushButton(tr("select_all"))
        b_none = QPushButton(tr("select_none"))
        br.addWidget(b_all)
        br.addWidget(b_none)
        lv.addLayout(br)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(4)
        self.progress.setVisible(False)
        lv.addWidget(self.progress)
        h.addWidget(left, 1)

        side = SidePanel()
        side.title(tr("details"))
        self.det = QLabel(tr("no_selection"))
        self.det.setObjectName("Details")
        self.det.setWordWrap(True)
        self.det.setTextFormat(Qt.RichText)
        self.det.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.det.setTextInteractionFlags(Qt.TextSelectableByMouse)
        side.lay.addWidget(self.det, 1)
        side.sep()
        side.title(tr("target"))
        self.target = PathPicker("dir")
        default = str(Path("D:/Drayverlar") if DEMO else documents_dir() / "Drayverlar")
        # Sozlamada ota papka saqlanadi, kompyuter nomi har safar qo'shiladi
        base = win.settings.get("target", "") if not DEMO and win.settings.get("target") else default
        self.target.set_path(os.path.join(base, os.environ.get("COMPUTERNAME", "PC") if not DEMO else "LENOVO-5-14IIL05"))
        side.lay.addWidget(self.target)
        self.by_class = QCheckBox(tr("by_class"))
        self.by_class.setChecked(True)
        self.zip = QCheckBox(tr("make_zip"))
        side.lay.addWidget(self.by_class)
        side.lay.addWidget(self.zip)
        side.sep()
        self.admin_note = QLabel(tr("admin_needed"))
        self.admin_note.setObjectName("Warn")
        self.admin_note.setWordWrap(True)
        self.admin_note.setVisible(not is_admin())
        side.lay.addWidget(self.admin_note)
        self.cmd_btn = QPushButton(tr("show_cmds"))
        side.lay.addWidget(self.cmd_btn)
        self.go = primary_button(tr("backup_btn", n=0))
        self.go.setIcon(svg_icon("download", "#ffffff"))
        side.lay.addWidget(self.go)
        h.addWidget(side)

        self.search.textChanged.connect(self._filter)
        self.cls.currentIndexChanged.connect(self._filter)
        self.hide_ms.toggled.connect(self._filter)
        self.table.itemChanged.connect(self._changed)
        self.table.currentCellChanged.connect(lambda r, *a: self._details(r))
        b_all.clicked.connect(lambda: self._check(True))
        b_none.clicked.connect(lambda: self._check(False))
        self.cmd_btn.clicked.connect(self._show_cmds)
        self.go.clicked.connect(self._backup)

    def set_items(self, items):
        self.items = items
        classes = sorted({d.cls for d in items if d.cls}, key=str.lower)
        self.cls.blockSignals(True)
        self.cls.clear()
        self.cls.addItem(tr("all_classes"), "")
        for c in classes:
            self.cls.addItem(c, c)
        self.cls.blockSignals(False)
        t = self.table
        t.blockSignals(True)
        t.setRowCount(len(items))
        for r, d in enumerate(items):
            t.setItem(r, 0, _it("", True, d.checked))
            p = _it(d.provider)
            p.setIcon(dot_icon("#e67700" if d.devices else "#adb5bd", 8))
            t.setItem(r, 1, p)
            t.setItem(r, 2, _it(d.cls))
            t.setItem(r, 3, _it(d.original))
            t.setItem(r, 4, _it(d.version))
            t.setItem(r, 5, _it(d.date))
            t.setItem(r, 6, _it(", ".join(d.devices) or "—"))
        t.blockSignals(False)
        self._filter()
        if items:
            t.selectRow(0)
            self._details(0)

    def _visible(self, d) -> bool:
        if self.hide_ms.isChecked() and d.is_microsoft:
            return False
        c = self.cls.currentData()
        if c and d.cls != c:
            return False
        q = self.search.text().strip().lower()
        if q:
            hay = " ".join([d.provider, d.original, d.cls, d.published, " ".join(d.devices)]).lower()
            return q in hay
        return True

    def _filter(self):
        shown = 0
        for r, d in enumerate(self.items):
            v = self._visible(d)
            self.table.setRowHidden(r, not v)
            shown += v
        self.count.setText(tr("found_n", n=len(self.items), m=shown))
        self._upd()

    def selected(self):
        return [d for r, d in enumerate(self.items) if d.checked and not self.table.isRowHidden(r)]

    def _upd(self):
        self.go.setText(tr("backup_btn", n=len(self.selected())))

    def _changed(self, it):
        if it.column() == 0 and 0 <= it.row() < len(self.items):
            self.items[it.row()].checked = it.checkState() == Qt.Checked
            self._upd()

    def _check(self, v):
        self.table.blockSignals(True)
        for r, d in enumerate(self.items):
            if not self.table.isRowHidden(r):
                d.checked = v
                self.table.item(r, 0).setCheckState(Qt.Checked if v else Qt.Unchecked)
        self.table.blockSignals(False)
        self._upd()

    def _details(self, r):
        if not (0 <= r < len(self.items)):
            self.det.setText(tr("no_selection"))
            return
        d = self.items[r]
        rows = [(tr("col_provider"), d.provider), (tr("col_class"), d.cls), (tr("col_inf"), d.original),
                (tr("col_published"), d.published), (tr("col_version"), d.version), (tr("col_date"), d.date),
                (tr("signer"), d.signer)]
        import html as h
        parts = [f"<div style='font-size:12pt; font-weight:600; margin-bottom:6px;'>{h.escape(d.original)}</div>"]
        parts.append("<table cellspacing='0' cellpadding='2'>")
        for k, v in rows:
            parts.append(f"<tr><td style='color:gray; padding-right:10px;'>{h.escape(k)}</td><td>{h.escape(v or '')}</td></tr>")
        parts.append("</table>")
        devs = "<br>".join(h.escape(x) for x in d.devices) or f"<span style='color:gray'>{h.escape(tr('not_used'))}</span>"
        parts.append(f"<p style='margin-top:8px;'><b>{h.escape(tr('col_devices'))}</b><br>{devs}</p>")
        self.det.setText("".join(parts))

    def _plan(self):
        dest = self.target.path()
        return drv.export_plan(self.selected(), dest or "<dest>", self.by_class.isChecked())

    def _show_cmds(self):
        plan = self._plan()
        if not plan:
            warn(self, tr("nothing_selected"))
            return
        CommandsDialog(self, [a for _, a in plan], [f for f, _ in plan]).exec()

    def _backup(self):
        sel = self.selected()
        dest = self.target.path()
        if not sel:
            warn(self, tr("nothing_selected"))
            return
        if not dest:
            warn(self, tr("no_target"))
            return
        dest = drv.resolve_target(dest)
        self.target.set_path(dest)
        if not is_admin():
            if ask(self, tr("admin_required")):
                do_relaunch(self)
            return
        if not ask(self, tr("confirm_backup", n=len(sel), dest=dest)):
            return
        if not DEMO:
            self.win.settings.set("target", os.path.dirname(dest))
        by_class, make_zip = self.by_class.isChecked(), self.zip.isChecked()
        windows = self.win.windows_caption()

        def job(progress):
            res = drv.run_export(sel, dest, by_class, progress, on_line=self.win.bridge.line.emit, windows=windows)
            if make_zip:
                res["zip"] = drv.zip_folder(dest, drv.zip_path_for(dest))
            return res
        self.win.run_job(job, self._done)

    def _done(self, res):
        msg = tr("backup_done", ok=res["ok"], err=res["failed"], file=drv.MANIFEST)
        if res.get("zip"):
            msg += "\n" + tr("zip_done", path=res["zip"])
        info(self, msg)
        open_path(self.target.path())


# =========================================================================== Tiklash
class RestorePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.entries = []
        self.setAcceptDrops(True)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(18, 14, 14, 14)
        lv.setSpacing(10)
        r = QHBoxLayout()
        r.addWidget(QLabel(tr("rs_folder")))
        self.folder = PathPicker("dir")
        r.addWidget(self.folder, 1)
        lv.addLayout(r)
        self.info = QLabel(tr("rs_hint"))
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        lv.addWidget(self.info)
        self.table = _table(["", tr("col_provider"), tr("col_class"), tr("col_inf"), tr("col_version"), tr("col_present"),
                             tr("col_folder")], 6)
        for i, w in enumerate([34, 170, 100, 140, 110, 90]):
            self.table.setColumnWidth(i, w)
        lv.addWidget(self.table, 1)
        h.addWidget(left, 1)

        side = SidePanel()
        side.title(tr("mode_restore"))
        note = QLabel(tr("restore_note"))
        note.setObjectName("Muted")
        note.setWordWrap(True)
        side.lay.addWidget(note)
        side.lay.addStretch(1)
        self.admin_note = QLabel(tr("admin_needed"))
        self.admin_note.setObjectName("Warn")
        self.admin_note.setWordWrap(True)
        self.admin_note.setVisible(not is_admin())
        side.lay.addWidget(self.admin_note)
        self.cmd_btn = QPushButton(tr("show_cmds"))
        side.lay.addWidget(self.cmd_btn)
        self.go = primary_button(tr("restore_btn", n=0))
        self.go.setIcon(svg_icon("upload", "#ffffff"))
        side.lay.addWidget(self.go)
        h.addWidget(side)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(700)
        self._timer.timeout.connect(lambda: self.load())
        self.folder.changed.connect(lambda _t: self._timer.start())
        self.table.itemChanged.connect(lambda it: self._upd())
        self.cmd_btn.clicked.connect(self._show_cmds)
        self.go.clicked.connect(self._restore)
        if DEMO:
            self._demo()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isdir(p):
                self.folder.set_path(os.path.normpath(p))
                return

    def load(self, path: str = None):
        path = path if path is not None else self.folder.path()
        self.entries = []
        if path and os.path.isdir(path):
            try:
                self.entries = drv.scan_backup(path)
                m = drv.read_manifest(path)
            except OSError as ex:
                error(self, str(ex))
                m = None
            if m:
                self.info.setText(tr("rs_info", pc=m.get("computer", ""), date=m.get("created", ""), n=len(self.entries)))
            elif self.entries:
                self.info.setText(tr("rs_no_manifest", n=len(self.entries)))
            else:
                self.info.setText(tr("rs_empty"))
        else:
            self.info.setText(tr("rs_hint"))
        self._fill()

    def _fill(self):
        t = self.table
        t.blockSignals(True)
        t.setRowCount(len(self.entries))
        for r, e in enumerate(self.entries):
            t.setItem(r, 0, _it("", True, e.get("exists", True)))
            t.setItem(r, 1, _it(e.get("provider")))
            t.setItem(r, 2, _it(e.get("cls")))
            t.setItem(r, 3, _it(e.get("original")))
            t.setItem(r, 4, _it(e.get("version")))
            p = _it(tr("present_yes") if e.get("exists", True) else tr("present_no"))
            p.setIcon(dot_icon("#2f9e44" if e.get("exists", True) else "#e03131", 8))
            t.setItem(r, 5, p)
            t.setItem(r, 6, _it(e.get("folder")))
        t.blockSignals(False)
        self._upd()

    def chosen(self):
        return [e for r, e in enumerate(self.entries)
                if self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.Checked and e.get("exists", True)]

    def _upd(self):
        self.go.setText(tr("restore_btn", n=len(self.chosen())))

    def _cmds(self):
        return drv.restore_plan(self.folder.path(), self.chosen())

    def _show_cmds(self):
        if not self.chosen():
            warn(self, tr("nothing_selected"))
            return
        CommandsDialog(self, self._cmds()).exec()

    def _restore(self):
        ch = self.chosen()
        if not ch:
            warn(self, tr("nothing_selected"))
            return
        if not is_admin():
            if ask(self, tr("admin_required")):
                do_relaunch(self)
            return
        if not ask(self, tr("confirm_restore", n=len(ch))):
            return
        cmds = self._cmds()
        self.win.run_job(lambda progress: drv.execute(cmds, progress, on_line=self.win.bridge.line.emit), self._done)

    def _done(self, res):
        ok = sum(1 for _, code, _ in res if code in drv.PNPUTIL_OK)
        info(self, tr("restore_done", ok=ok, err=len(res) - ok) + "\n" + tr("restore_note"))

    def _demo(self):
        self.folder.edit.blockSignals(True)
        self.folder.set_path(r"E:\Zaxira\Drayverlar\LENOVO-5-14IIL05")
        self.folder.edit.blockSignals(False)
        self.entries = []
        for d in demo_drivers():
            if d.is_microsoft:
                continue
            e = d.to_dict()
            e["folder"] = f"{d.cls}/{d.folder_name()}"
            e["exists"] = d.original != "cardreader.inf"
            self.entries.append(e)
        self.info.setText(tr("rs_info", pc="LENOVO-5-14IIL05", date="2026-11-20 18:42:10", n=len(self.entries)))
        self._fill()


# =========================================================================== Jurnal
class LogPage(QWidget):
    def __init__(self, win):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        top = QHBoxLayout()
        t = QLabel(tr("log_title"))
        t.setObjectName("PanelTitle")
        top.addWidget(t, 1)
        b = QPushButton(tr("save_log"))
        top.addWidget(b)
        lay.addLayout(top)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName("Mono")
        self.text.setPlaceholderText(tr("log_empty"))
        lay.addWidget(self.text, 1)
        b.clicked.connect(self._save)
        if DEMO:
            for d in demo_drivers()[:4]:
                folder = rf"D:\Drayverlar\LENOVO-5-14IIL05\{d.cls}\{d.folder_name()}"
                self.add(f"> pnputil.exe /export-driver {d.published} {folder}\n"
                         f"Exporting driver package:   {d.original} ({d.published})\n"
                         "Driver package exported successfully.\n[0]")

    def add(self, text):
        self.text.appendPlainText(f"[{datetime.now():%H:%M:%S}] {text}\n")

    def _save(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("save_log"), str(documents_dir() / "drayver_jurnal.txt"), "Text (*.txt)")
        if p:
            Path(p).write_text(self.text.toPlainText(), encoding="utf-8")


# =========================================================================== Asosiy oyna
class MainWindow(BaseMainWindow):
    def __init__(self):
        super().__init__()
        self.job = None
        self.bridge = _Bridge()
        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        strip = QFrame()
        strip.setObjectName("ToolStrip")
        sh = QHBoxLayout(strip)
        sh.setContentsMargins(14, 6, 14, 0)
        sh.setSpacing(8)
        logo = QLabel()
        ip = resource("assets", "icon.png")
        if ip.exists():
            logo.setPixmap(QPixmap(str(ip)).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        sh.addWidget(logo, 0, Qt.AlignVCenter)
        self._nav = QTabBar()
        self._nav.setObjectName("ModeTabs")
        self._nav.setDrawBase(False)
        sh.addWidget(self._nav, 0, Qt.AlignBottom)
        sh.addStretch(1)
        self.refresh_btn = QPushButton(svg_icon("refresh", "#868e96"), tr("refresh"))
        self.refresh_btn.setObjectName("ToolButton")
        sh.addWidget(self.refresh_btn, 0, Qt.AlignVCenter)
        chip = QLabel(tr("admin_on") if is_admin() else tr("admin_off"))
        chip.setObjectName("AdminChip" if is_admin() else "UserChip")
        sh.addWidget(chip, 0, Qt.AlignVCenter)
        if not is_admin():
            rb = QPushButton(svg_icon("shield", "#868e96"), tr("admin_relaunch"))
            rb.setObjectName("ToolButton")
            rb.clicked.connect(lambda: do_relaunch(self))
            sh.addWidget(rb, 0, Qt.AlignVCenter)
        v.addWidget(strip)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(3)
        self.bar.setObjectName("JobBar")
        self.bar.setVisible(False)
        v.addWidget(self.bar)
        self._stack = QStackedWidget()
        v.addWidget(self._stack, 1)
        self.setCentralWidget(root)

        self.backup = BackupPage(self)
        self.restore = RestorePage(self)
        self.log = LogPage(self)
        for w, title, ic in ((self.backup, "mode_backup", "download"), (self.restore, "mode_restore", "upload"),
                             (self.log, "mode_log", "list")):
            self._stack.addWidget(w)
            self._nav.addTab(svg_icon(ic, "#868e96"), tr(title))
        self._nav.currentChanged.connect(self._stack.setCurrentIndex)
        self.bridge.line.connect(self.log.add)
        self.refresh_btn.clicked.connect(self.load)
        if DEMO:
            self.backup.set_items(demo_drivers())
        elif AUTO:
            self.load()

    def set_page(self, i: int):
        if 0 <= i < self._nav.count():
            self._nav.setCurrentIndex(i)

    def windows_caption(self) -> str:
        import platform
        return f"{platform.system()} {platform.release()} {platform.version()}"

    def load(self):
        if self.job is not None:
            return
        self.status(tr("loading"), 0)
        self.run_job(drv.list_drivers, self._loaded)

    def _loaded(self, items):
        self.backup.set_items(items)
        self.status(tr("found_n", n=len(items), m=sum(1 for d in items if not d.is_microsoft)))

    def run_job(self, fn, on_done):
        if self.job is not None:
            return
        self.bar.setVisible(True)
        self.bar.setValue(0)
        self.backup.go.setEnabled(False)
        self.restore.go.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.job = Worker(fn)
        self.job.signals.progress.connect(lambda p, m: (self.bar.setValue(p), m and self.status(tr("working_on", name=m))))
        self.job.signals.result.connect(on_done)
        self.job.signals.error.connect(lambda e: error(self, e))
        self.job.signals.finished.connect(self._job_end)
        run_worker(self.job)

    def closeEvent(self, e):
        if self.job is not None:
            self.job.cancel()
        super().closeEvent(e)
        self.hide()
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(15000)

    def _job_end(self):
        self.job = None
        self.bar.setVisible(False)
        self.backup.go.setEnabled(True)
        self.restore.go.setEnabled(True)
        self.refresh_btn.setEnabled(True)
