"""Flashing: single partition, whole firmware folder, bootloader ops, sideload."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QGridLayout, QHeaderView,
    QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ...core.runner import Job
from ..widgets import FilePicker, button, card, hbox, human_size, label, page_header

PARTITIONS = [
    "boot", "init_boot", "vendor_boot", "recovery", "dtbo", "vbmeta", "vbmeta_system",
    "vbmeta_vendor", "super", "system", "system_ext", "product", "vendor", "vendor_dlkm",
    "odm", "userdata", "cache", "bootloader", "radio", "modem", "persist", "logo", "splash",
]
LOGICAL = {"system", "system_ext", "product", "vendor", "vendor_dlkm", "odm", "odm_dlkm", "system_dlkm"}
# order used when flashing a whole folder
ORDER = ["bootloader", "radio", "modem", "abl", "xbl", "xbl_config", "tz", "hyp", "keymaster",
         "dsp", "bluetooth", "devcfg", "aop", "dtbo", "vbmeta", "vbmeta_system", "vbmeta_vendor",
         "boot", "init_boot", "vendor_boot", "vendor_kernel_boot", "recovery", "super"]
UNCHECKED_BY_DEFAULT = {"userdata", "cache", "persist", "metadata", "misc", "frp"}
SLOTS = [("По умолчанию", ""), ("Слот A", "a"), ("Слот B", "b"), ("Оба слота", "all")]


def guess_partition(path: str) -> str:
    stem = Path(path).stem.lower()
    for prefix in ("bootloader", "radio"):
        if stem.startswith(prefix):
            return prefix
    if stem.startswith("magisk_patched") or stem.startswith("patched"):
        return "init_boot" if "init" in stem else "boot"
    return stem


class FlashPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 12)
        lay.setSpacing(14)
        lay.addLayout(page_header("⚡ Прошивка", "Прошивка разделов, установка целых прошивок из папки, "
                                                 "управление загрузчиком и sideload."))
        self.mode_hint = label("", "hint", wrap=True)
        self.mode_btn = button("⚡ Перезагрузить в Bootloader", lambda: app.reboot("bootloader"))
        hint_row = hbox(self.mode_hint, self.mode_btn)
        hint_row.setStretch(0, 1)
        lay.addLayout(hint_row)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._scroll(self._tab_single()), "🎯 Раздел")
        self.tabs.addTab(self._tab_folder(), "📁 Прошивка из папки")
        self.tabs.addTab(self._scroll(self._tab_bootloader()), "🔓 Загрузчик")
        self.tabs.addTab(self._scroll(self._tab_sideload()), "📦 Sideload / ZIP")
        self.tabs.addTab(self._scroll(self._tab_gsi()), "🧬 GSI")
        lay.addWidget(self.tabs, 1)

        app.deviceChanged.connect(self._on_device)
        self._on_device(app.device)

    @staticmethod
    def _scroll(w: QWidget) -> QScrollArea:
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setWidget(w)
        return s

    def _on_device(self, dev) -> None:
        if dev is None:
            self.mode_hint.setText("🔌 Устройство не подключено. Для прошивки переведите его в режим Bootloader (Fastboot).")
            self.mode_btn.hide()
        elif dev.is_fastboot:
            self.mode_hint.setText("✅ Устройство в режиме Fastboot — можно прошивать.")
            self.mode_hint.setStyleSheet("color:#2ee6a6; background: rgba(46,230,166,0.08); border-color: rgba(46,230,166,0.35);")
            self.mode_btn.hide()
            return
        else:
            self.mode_hint.setText(f"Устройство в режиме «{dev.mode_name}». Команды fastboot сначала автоматически перезагрузят его в Bootloader.")
            self.mode_btn.setVisible(dev.is_adb)
        self.mode_hint.setStyleSheet("")

    # ============================================================ helpers
    def _prepare_fastboot(self) -> list[Job] | None:
        """Jobs needed before fastboot commands (reboot to bootloader) or None if cancelled."""
        dev = self.app.device
        if dev is None:
            if self.app.confirm("Нет устройства", "Устройство не обнаружено. Запустить всё равно? "
                                "fastboot будет ждать подключения устройства.", danger=False):
                return []
            return None
        if dev.is_fastboot:
            return []
        if dev.is_adb:
            if self.app.confirm("Перезагрузка в Bootloader",
                                f"Устройство в режиме «{dev.mode_name}». Перезагрузить в Bootloader и продолжить?",
                                danger=False):
                return [self.app.adb_job("reboot", "bootloader", label="Перезагрузка в Bootloader")]
            return None
        self.app.notify(f"Устройство в режиме «{dev.mode_name}» — нужен Fastboot", "warn")
        return None

    @staticmethod
    def _slot_args(combo: QComboBox) -> list[str]:
        slot = combo.currentData()
        return [f"--slot={slot}"] if slot else []

    # ============================================================ single
    def _tab_single(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        c, cl = card("🎯 Прошить один раздел", "Выберите образ — раздел определится по имени файла автоматически.")
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.s_file = FilePicker("Перетащите .img файл сюда", "Образы (*.img *.bin *.mbn *.elf);;Все файлы (*)",
                                 config=self.app.config, key="img")
        self.s_file.changed.connect(self._on_single_file)
        self.s_part = QComboBox()
        self.s_part.setEditable(True)
        self.s_part.addItems(PARTITIONS)
        self.s_part.currentTextChanged.connect(self._on_part_changed)
        self.s_slot = QComboBox()
        for name, val in SLOTS:
            self.s_slot.addItem(name, val)
        self.s_info = label("", "muted")
        form.addRow("Файл образа", self.s_file)
        form.addRow("Раздел", hbox(self.s_part, self.s_info, None))
        form.addRow("Слот", hbox(self.s_slot, None))
        cl.addLayout(form)
        self.s_verity = QCheckBox("Отключить verity / verification (--disable-verity --disable-verification)")
        self.s_verity.setEnabled(False)
        self.s_reboot = QCheckBox("Перезагрузить в систему после прошивки")
        cl.addWidget(self.s_verity)
        cl.addWidget(self.s_reboot)
        cl.addLayout(hbox(
            button("⚡ Прошить", self.flash_single, "accent"),
            button("🧪 Загрузить без прошивки", self.boot_single,
                   tip="fastboot boot — однократная загрузка образа (удобно для проверки boot/recovery)"),
            None,
            button("🧹 Стереть раздел", self.erase_single, "danger"),
        ))
        lay.addWidget(c)

        tips, tl = card("💡 Подсказки")
        tl.addWidget(label(
            "• <b>Magisk / KernelSU:</b> пропатчите boot.img (или init_boot.img на Android 13+) и прошейте сюда.<br>"
            "• <b>Динамические разделы</b> (system, vendor, product…) прошиваются из <b>fastbootd</b> — "
            "кнопка «Fastbootd» в меню перезагрузки.<br>"
            "• <b>vbmeta</b> с отключением verity нужен для кастомных GSI/ядер.<br>"
            "• Сначала попробуйте «Загрузить без прошивки» — если не загрузится, ничего не сломается.",
            "muted", wrap=True))
        lay.addWidget(tips)
        lay.addStretch(1)
        return w

    def _on_single_file(self, path: str) -> None:
        if not path:
            return
        part = guess_partition(path)
        self.s_part.setCurrentText(part)
        try:
            self.s_info.setText(human_size(Path(path).stat().st_size))
        except OSError:
            self.s_info.setText("")

    def _on_part_changed(self, part: str) -> None:
        is_vbmeta = part.startswith("vbmeta")
        self.s_verity.setEnabled(is_vbmeta)
        if not is_vbmeta:
            self.s_verity.setChecked(False)
        if part in LOGICAL:
            self.s_info.setText("⚠ логический раздел — нужен fastbootd")

    def _single_checked(self) -> tuple[str, str] | None:
        path, part = self.s_file.path(), self.s_part.currentText().strip()
        if not path or not Path(path).is_file():
            self.app.notify("Выберите файл образа", "warn")
            return None
        if not part:
            self.app.notify("Укажите раздел", "warn")
            return None
        return path, part

    def flash_single(self) -> None:
        sel = self._single_checked()
        if not sel:
            return
        path, part = sel
        if not self.app.confirm("Прошивка раздела", f"Прошить <b>{part}</b> файлом<br><code>{Path(path).name}</code>?"):
            return
        pre = self._prepare_fastboot()
        if pre is None:
            return
        args = self._slot_args(self.s_slot)
        if self.s_verity.isChecked():
            args += ["--disable-verity", "--disable-verification"]
        jobs = pre + [self.app.fb_job(*args, "flash", part, path, label=f"Прошивка {part}")]
        if self.s_reboot.isChecked():
            jobs.append(self.app.fb_job("reboot"))
        self.app.run(jobs)

    def boot_single(self) -> None:
        sel = self._single_checked()
        if not sel:
            return
        pre = self._prepare_fastboot()
        if pre is not None:
            self.app.run(pre + [self.app.fb_job("boot", sel[0], label="Временная загрузка образа")])

    def erase_single(self) -> None:
        part = self.s_part.currentText().strip()
        if not part:
            return
        if not self.app.confirm("Стереть раздел", f"Раздел <b>{part}</b> будет полностью стёрт. Это необратимо!"):
            return
        pre = self._prepare_fastboot()
        if pre is not None:
            self.app.run(pre + [self.app.fb_job(*self._slot_args(self.s_slot), "erase", part)])

    # ============================================================ folder
    def _tab_folder(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)
        lay.addWidget(label("Выберите распакованную фабричную прошивку (папку с *.img). Образы будут прошиты "
                            "в правильном порядке: bootloader → radio → vbmeta → boot → … → логические разделы.",
                            "muted", wrap=True))
        self.f_dir = FilePicker("Перетащите папку с прошивкой", mode="dir", config=self.app.config, key="fw")
        self.f_dir.changed.connect(self.scan_folder)
        lay.addWidget(self.f_dir)

        self.f_required: list[str] = []
        self.f_table = QTableWidget(0, 4)
        self.f_table.setHorizontalHeaderLabels(["", "Раздел", "Файл", "Размер"])
        hh = self.f_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.f_table.verticalHeader().hide()
        self.f_table.setAlternatingRowColors(True)
        self.f_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.f_table, 1)

        self.f_status = label("Папка не выбрана", "muted")
        lay.addLayout(hbox(
            self.f_status, None,
            button("☑ Все", lambda: self._check_all(True), "ghost"),
            button("☐ Ничего", lambda: self._check_all(False), "ghost"),
        ))

        opts = QGridLayout()
        opts.setHorizontalSpacing(24)
        self.f_slot = QComboBox()
        for name, val in SLOTS:
            self.f_slot.addItem(name, val)
        self.f_wipe = QCheckBox("Сброс данных (fastboot -w)")
        self.f_verity = QCheckBox("Отключить verity для vbmeta")
        self.f_fastbootd = QCheckBox("Логические разделы через fastbootd")
        self.f_fastbootd.setChecked(True)
        self.f_fastbootd.setToolTip("Перед system/vendor/product автоматически выполнит «fastboot reboot fastboot»")
        self.f_reboot = QCheckBox("Перезагрузить в систему в конце")
        self.f_reboot.setChecked(True)
        opts.addWidget(self.f_wipe, 0, 0)
        opts.addWidget(self.f_verity, 0, 1)
        opts.addWidget(self.f_fastbootd, 1, 0)
        opts.addWidget(self.f_reboot, 1, 1)
        opts.addLayout(hbox(label("Слот:", "muted"), self.f_slot, None), 0, 2)
        lay.addLayout(opts)
        lay.addLayout(hbox(None, button("⚡ Прошить выбранное", self.flash_folder, "accent")))
        return w

    def scan_folder(self, folder: str) -> None:
        root = Path(folder)
        if not root.is_dir():
            return
        images = sorted(p for p in root.rglob("*.img") if p.is_file())
        rank = {name: i for i, name in enumerate(ORDER)}

        def key(p: Path):
            part = guess_partition(str(p))
            if part in LOGICAL:
                return (2, part)
            return (0, rank.get(part, len(ORDER)), part) if part in rank else (1, 0, part)

        images.sort(key=key)
        self.f_table.setRowCount(len(images))
        for row, p in enumerate(images):
            part = guess_partition(str(p))
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked if part in UNCHECKED_BY_DEFAULT else Qt.CheckState.Checked)
            self.f_table.setItem(row, 0, chk)
            pi = QTableWidgetItem(part)
            pi.setToolTip("Двойной клик — изменить раздел")
            if part in LOGICAL:
                pi.setForeground(Qt.GlobalColor.yellow)
            self.f_table.setItem(row, 1, pi)
            fi = QTableWidgetItem(str(p.relative_to(root)))
            fi.setData(Qt.ItemDataRole.UserRole, str(p))
            fi.setFlags(fi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.f_table.setItem(row, 2, fi)
            si = QTableWidgetItem(human_size(p.stat().st_size))
            si.setFlags(si.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.f_table.setItem(row, 3, si)
        self.f_required = self._read_android_info(root)
        scripts = [s.name for s in root.glob("flash-all.*")] + [s.name for s in root.glob("*.zip")]
        msg = f"Найдено образов: {len(images)}"
        if scripts:
            msg += f"   ·   также в папке: {', '.join(scripts[:4])}"
        if self.f_required:
            msg += f"   ·   🎯 для устройства: {', '.join(self.f_required)}"
        self.f_status.setText(msg)

    @staticmethod
    def _read_android_info(root: Path) -> list[str]:
        """Board names from android-info.txt ('require board=panther|cheetah')."""
        for f in [root / "android-info.txt", *root.glob("*/android-info.txt")]:
            try:
                for line in f.read_text(errors="replace").splitlines():
                    key, _, val = line.strip().partition("=")
                    if key.replace("require", "").strip() in ("board", "product"):
                        return [b.strip() for b in val.split("|") if b.strip()]
            except OSError:
                continue
        return []

    def _device_codename(self) -> str:
        props = self.app.page_dashboard.props
        return (props.get("product") or props.get("ro.product.device") or props.get("ro.product.board") or "").lower()

    def _check_all(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for r in range(self.f_table.rowCount()):
            self.f_table.item(r, 0).setCheckState(state)

    def flash_folder(self) -> None:
        items = []
        for r in range(self.f_table.rowCount()):
            if self.f_table.item(r, 0).checkState() == Qt.CheckState.Checked:
                items.append((self.f_table.item(r, 1).text().strip(),
                              self.f_table.item(r, 2).data(Qt.ItemDataRole.UserRole)))
        if not items:
            self.app.notify("Ничего не выбрано", "warn")
            return
        codename = self._device_codename()
        if self.f_required and codename and codename not in [b.lower() for b in self.f_required]:
            if not self.app.confirm("⚠ Прошивка для другого устройства!",
                                    f"Прошивка предназначена для <b>{', '.join(self.f_required)}</b>, "
                                    f"а подключено устройство <b>{codename}</b>.<br><br>"
                                    "Прошивка чужого образа почти наверняка превратит телефон в «кирпич». "
                                    "Продолжать только если вы точно знаете, что делаете."):
                return
        names = ", ".join(p for p, _ in items)
        warn = "<br><br><b style='color:#ff4d6d'>Все данные пользователя будут удалены!</b>" if self.f_wipe.isChecked() else ""
        if not self.app.confirm("Прошивка из папки",
                                f"Будет прошито разделов: <b>{len(items)}</b><br><small>{names}</small>{warn}<br><br>"
                                "Не отключайте устройство до окончания!"):
            return
        pre = self._prepare_fastboot()
        if pre is None:
            return
        slot = self._slot_args(self.f_slot)
        jobs = list(pre)
        in_fastbootd = False
        for part, path in items:
            if part in LOGICAL and self.f_fastbootd.isChecked() and not in_fastbootd:
                jobs.append(self.app.fb_job("reboot", "fastboot", label="Переход в fastbootd для логических разделов"))
                in_fastbootd = True
            args = list(slot)
            if part.startswith("vbmeta") and self.f_verity.isChecked():
                args += ["--disable-verity", "--disable-verification"]
            jobs.append(self.app.fb_job(*args, "flash", part, path, label=f"Прошивка {part}"))
            if part in ("bootloader", "radio"):
                jobs.append(self.app.fb_job("reboot", "bootloader", label="Перезагрузка загрузчика"))
        if self.f_wipe.isChecked():
            jobs.append(self.app.fb_job("-w", label="Сброс данных"))
        if self.f_reboot.isChecked():
            jobs.append(self.app.fb_job("reboot"))
        self.app.run(jobs, stop_on_error=True)

    # ============================================================ bootloader
    def _tab_bootloader(self) -> QWidget:
        w = QWidget()
        lay = QGridLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)
        fb = lambda *a, **kw: lambda: self._fb(list(a), **kw)  # noqa: E731

        c1, l1 = card("🔍 Статус загрузчика")
        l1.addWidget(button("📋 getvar all", fb("getvar", "all")))
        l1.addLayout(hbox(button("🔒 unlocked?", fb("getvar", "unlocked")),
                          button("🅰 current-slot", fb("getvar", "current-slot"))))
        l1.addLayout(hbox(button("🧩 is-userspace", fb("getvar", "is-userspace")),
                          button("ℹ oem device-info", fb("oem", "device-info"))))
        l1.addWidget(button("❓ Можно разблокировать?", fb("flashing", "get_unlock_ability")))
        l1.addStretch(1)
        lay.addWidget(c1, 0, 0)

        c2, l2 = card("🔓 Разблокировка / блокировка",
                      "Разблокировка удаляет ВСЕ данные. Включите «Заводская разблокировка» (OEM unlock) "
                      "в параметрах разработчика. Xiaomi требует официальный Mi Unlock.")
        warn_unlock = "Все данные на устройстве будут удалены! Подтвердите действие на экране телефона кнопками громкости."
        l2.addLayout(hbox(
            button("🔓 flashing unlock", fb("flashing", "unlock", confirm=warn_unlock), "danger"),
            button("🔒 flashing lock", fb("flashing", "lock", confirm="Блокировка с НЕоригинальной прошивкой может превратить устройство в «кирпич»! Данные будут удалены."), "danger"),
        ))
        l2.addLayout(hbox(
            button("🔓 unlock_critical", fb("flashing", "unlock_critical", confirm=warn_unlock), "danger"),
            button("🔓 oem unlock (старые)", fb("oem", "unlock", confirm=warn_unlock), "danger"),
        ))
        l2.addStretch(1)
        lay.addWidget(c2, 0, 1)

        c3, l3 = card("🅰🅱 A/B слоты", "Переключение активного слота загрузки.")
        l3.addLayout(hbox(
            button("Сделать активным A", fb("set_active", "a", confirm="Переключить активный слот на A?")),
            button("Сделать активным B", fb("set_active", "b", confirm="Переключить активный слот на B?")),
        ))
        l3.addStretch(1)
        lay.addWidget(c3, 1, 0)

        c4, l4 = card("🧰 Прочее")
        l4.addLayout(hbox(
            button("▶ continue", fb("continue"), tip="Продолжить обычную загрузку"),
            button("🧩 → fastbootd", fb("reboot", "fastboot")),
            button("⚡ → bootloader", fb("reboot", "bootloader")),
        ))
        l4.addWidget(button("🧨 Сброс данных (fastboot -w)",
                            fb("-w", confirm="userdata и cache будут стёрты. Продолжить?"), "danger"))
        l4.addStretch(1)
        lay.addWidget(c4, 1, 1)
        lay.setRowStretch(2, 1)
        return w

    def _fb(self, args: list[str], confirm: str | None = None) -> None:
        if confirm and not self.app.confirm("Подтверждение", confirm):
            return
        pre = self._prepare_fastboot()
        if pre is not None:
            self.app.run(pre + [self.app.fb_job(*args)])

    # ============================================================ sideload
    def _tab_sideload(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        c, cl = card("📦 ADB Sideload", "Установка OTA / кастомных прошивок / Magisk через recovery. "
                                       "В recovery выберите «Apply update → Apply from ADB».")
        self.z_file = FilePicker("Перетащите .zip сюда", "ZIP архивы (*.zip);;Все файлы (*)",
                                 exts=(".zip",), config=self.app.config, key="zip")
        cl.addWidget(self.z_file)
        cl.addLayout(hbox(
            button("📦 adb sideload", self.sideload, "accent"),
            button("🔁 Перезагрузить в Sideload", lambda: self.app.reboot("sideload")),
            button("🛠 Перезагрузить в Recovery", lambda: self.app.reboot("recovery")),
            None,
        ))
        lay.addWidget(c)

        c2, l2 = card("🗜 fastboot update", "Прошивка update-архива (image-*.zip из фабричных образов Pixel и т.п.).")
        self.u_file = FilePicker("Перетащите image-*.zip сюда", "ZIP архивы (*.zip)",
                                 exts=(".zip",), config=self.app.config, key="zip")
        self.u_wipe = QCheckBox("С очисткой данных (-w)")
        self.u_skip = QCheckBox("Не перезагружаться после (--skip-reboot)")
        l2.addWidget(self.u_file)
        l2.addLayout(hbox(self.u_wipe, self.u_skip, None, button("⚡ fastboot update", self.fb_update, "accent")))
        lay.addWidget(c2)
        lay.addStretch(1)
        return w

    def sideload(self) -> None:
        path = self.z_file.path()
        if not Path(path).is_file():
            self.app.notify("Выберите ZIP файл", "warn")
            return
        dev = self.app.device
        if dev and dev.mode not in ("sideload", "recovery"):
            self.app.notify("Устройство должно быть в режиме sideload (recovery → Apply from ADB)", "warn")
        self.app.run([self.app.adb_job("sideload", path, label=f"Sideload {Path(path).name}")])

    def fb_update(self) -> None:
        path = self.u_file.path()
        if not Path(path).is_file():
            self.app.notify("Выберите ZIP файл", "warn")
            return
        args = []
        if self.u_wipe.isChecked():
            args.append("-w")
        if self.u_skip.isChecked():
            args.append("--skip-reboot")
        text = f"Прошить <code>{Path(path).name}</code>?"
        if self.u_wipe.isChecked():
            text += "<br><b>Данные будут удалены!</b>"
        if not self.app.confirm("fastboot update", text):
            return
        pre = self._prepare_fastboot()
        if pre is not None:
            self.app.run(pre + [self.app.fb_job(*args, "update", path, label="fastboot update")])

    # ============================================================ GSI
    def _tab_gsi(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)
        c, cl = card("🧬 Установка GSI (Generic System Image)",
                     "Чистый Android или кастомная система на любом устройстве с Project Treble. "
                     "Нужен разблокированный загрузчик. Архивы .xz / .zip сначала распакуйте до .img.")
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.g_img = FilePicker("Перетащите system.img (GSI)", "Образы (*.img)", exts=(".img",),
                                config=self.app.config, key="gsi")
        self.g_vbmeta = FilePicker("vbmeta.img от вашей стоковой прошивки (рекомендуется)", "Образы (*.img)",
                                   exts=(".img",), config=self.app.config, key="img")
        form.addRow("GSI образ", self.g_img)
        form.addRow("vbmeta", self.g_vbmeta)
        cl.addLayout(form)
        self.g_product = QCheckBox("Удалить раздел product, если не хватает места (delete-logical-partition)")
        self.g_wipe = QCheckBox("Сброс данных (обязательно при переходе со стока)")
        self.g_wipe.setChecked(True)
        self.g_reboot = QCheckBox("Перезагрузить в систему в конце")
        self.g_reboot.setChecked(True)
        for box in (self.g_product, self.g_wipe, self.g_reboot):
            cl.addWidget(box)
        cl.addLayout(hbox(button("🔍 Проверить поддержку Treble", self.check_treble), None,
                          button("🧬 Установить GSI", self.flash_gsi, "accent")))
        lay.addWidget(c)

        steps, sl = card("📋 Что будет выполнено")
        sl.addWidget(label(
            "1. Перезагрузка в bootloader (если нужно)<br>"
            "2. <code>fastboot --disable-verity --disable-verification flash vbmeta vbmeta.img</code><br>"
            "3. <code>fastboot reboot fastboot</code> — переход в fastbootd<br>"
            "4. (опц.) <code>fastboot delete-logical-partition product_a</code><br>"
            "5. <code>fastboot erase system</code> и <code>fastboot flash system gsi.img</code><br>"
            "6. <code>fastboot -w</code> и перезагрузка", "muted", wrap=True))
        lay.addWidget(steps)
        lay.addStretch(1)
        return w

    def check_treble(self) -> None:
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", "echo treble=$(getprop ro.treble.enabled) "
                                           "dynamic=$(getprop ro.boot.dynamic_partitions) "
                                           "ab=$(getprop ro.build.ab_update) arch=$(getprop ro.product.cpu.abi) "
                                           "vndk=$(getprop ro.vndk.version)")])

    def flash_gsi(self) -> None:
        img, vbmeta = self.g_img.path(), self.g_vbmeta.path()
        if not Path(img).is_file():
            self.app.notify("Выберите GSI образ", "warn")
            return
        warn = "<br><b>Все данные будут удалены!</b>" if self.g_wipe.isChecked() else ""
        if not vbmeta:
            warn += "<br>⚠ vbmeta не указан — без отключения проверки система может не загрузиться."
        if not self.app.confirm("Установка GSI", f"Прошить <code>{Path(img).name}</code> в раздел system?{warn}"):
            return
        pre = self._prepare_fastboot()
        if pre is None:
            return
        jobs = list(pre)
        if vbmeta and Path(vbmeta).is_file():
            jobs.append(self.app.fb_job("--disable-verity", "--disable-verification", "flash", "vbmeta", vbmeta,
                                        label="vbmeta без проверки"))
        jobs.append(self.app.fb_job("reboot", "fastboot", label="Переход в fastbootd"))
        if self.g_product.isChecked():
            for suffix in ("_a", "_b"):
                jobs.append(self.app.fb_job("delete-logical-partition", f"product{suffix}", allow_fail=True))
        jobs.append(self.app.fb_job("erase", "system", allow_fail=True))
        jobs.append(self.app.fb_job("flash", "system", img, label="Прошивка GSI"))
        if self.g_wipe.isChecked():
            jobs.append(self.app.fb_job("-w", label="Сброс данных"))
        if self.g_reboot.isChecked():
            jobs.append(self.app.fb_job("reboot"))
        self.app.run(jobs, stop_on_error=True)
