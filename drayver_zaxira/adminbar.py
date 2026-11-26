"""Administrator huquqi yo'qligi haqida panel + "administrator sifatida qayta ishga tushirish" tugmasi."""
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton

from uzkit.i18n import register, tr
from uzkit.widgets import Card, error, is_admin, relaunch_as_admin

from .ui import svg_icon

register({
    "admin_banner": {
        "uz": "Dastur oddiy foydalanuvchi huquqida ishlayapti. Ba'zi amallar uchun administrator huquqi kerak.",
        "ru": "Программа запущена без прав администратора. Для некоторых действий нужны права администратора.",
        "en": "The app is running without administrator rights. Some actions require administrator rights.",
    },
    "admin_relaunch": {"uz": "Administrator sifatida ochish", "ru": "Запустить от имени администратора",
                       "en": "Restart as administrator"},
    "admin_relaunch_fail": {"uz": "Administrator sifatida ishga tushirib bo'lmadi.",
                            "ru": "Не удалось запустить от имени администратора.",
                            "en": "Could not restart as administrator."},
    "admin_on": {"uz": "Administrator huquqi bor", "ru": "Права администратора есть", "en": "Running as administrator"},
})


def do_relaunch(parent=None):
    """Foydalanuvchi tugmani bosganda chaqiriladi (UAC oynasi chiqadi)."""
    if relaunch_as_admin():
        QApplication.quit()
    else:
        error(parent, tr("admin_relaunch_fail"))


class AdminBanner(Card):
    def __init__(self, parent=None, force_show: bool = False):
        super().__init__(parent=parent)
        self.setObjectName("AdminBanner")
        self.lay.setContentsMargins(14, 8, 10, 8)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(svg_icon("shield", "#c27c0e").pixmap(22, 22))
        row.addWidget(ic)
        t = QLabel(tr("admin_banner"))
        t.setWordWrap(True)
        row.addWidget(t, 1)
        b = QPushButton(tr("admin_relaunch"))
        b.clicked.connect(lambda: do_relaunch(self))
        row.addWidget(b)
        self.add(row)
        self.setVisible(force_show or not is_admin())
