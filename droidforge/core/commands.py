"""Command-line parsing for the console and the quick-command library."""
from __future__ import annotations

import os
import shlex

# Commands that never need "-s <serial>"
NO_SERIAL = {
    "adb": {"devices", "connect", "disconnect", "pair", "kill-server", "start-server",
            "version", "help", "mdns", "keygen"},
    "fastboot": {"devices", "help", "--version", "version"},
}


def split_command(text: str) -> list[list[str]]:
    """Split a command line into commands separated by '&&'."""
    posix = os.name != "nt"
    tokens = shlex.split(text, posix=posix)
    if not posix:
        tokens = [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t for t in tokens]
    commands: list[list[str]] = [[]]
    for tok in tokens:
        if tok == "&&":
            commands.append([])
        else:
            commands[-1].append(tok)
    return [c for c in commands if c]


# --------------------------------------------------------------------------
# Quick command library: category -> [(title, command, description, danger)]
# --------------------------------------------------------------------------
PRESETS: dict[str, list[tuple[str, str, str, bool]]] = {
    "🔌 Подключение": [
        ("Список устройств", "adb devices -l", "Все устройства, видимые adb", False),
        ("Fastboot устройства", "fastboot devices", "Устройства в режиме fastboot", False),
        ("Перезапуск ADB сервера", "adb kill-server && adb start-server", "Помогает при «offline»", False),
        ("ADB по Wi‑Fi (порт 5555)", "adb tcpip 5555", "Переключить adbd на TCP", False),
        ("Вернуть ADB на USB", "adb usb", "Переключить adbd обратно на USB", False),
        ("Отключить все Wi‑Fi", "adb disconnect", "Разорвать все TCP подключения", False),
        ("Версия ADB", "adb version", "Версия platform-tools", False),
    ],
    "🔄 Перезагрузка": [
        ("В систему", "adb reboot", "Обычная перезагрузка", False),
        ("В Recovery", "adb reboot recovery", "Режим восстановления", False),
        ("В Bootloader", "adb reboot bootloader", "Fastboot / загрузчик", False),
        ("В Fastbootd", "adb reboot fastboot", "Userspace fastboot (динамические разделы)", False),
        ("В Sideload", "adb reboot sideload", "Режим adb sideload", False),
        ("В EDL (Qualcomm)", "adb reboot edl", "Emergency Download Mode", True),
        ("Выключить", "adb shell reboot -p", "Выключение устройства", False),
    ],
    "📊 Информация": [
        ("Батарея", "adb shell dumpsys battery", "Уровень, температура, статус", False),
        ("Версия Android", "adb shell getprop ro.build.version.release", "", False),
        ("Модель", "adb shell getprop ro.product.model", "", False),
        ("Отпечаток сборки", "adb shell getprop ro.build.fingerprint", "", False),
        ("Текущий слот", "adb shell getprop ro.boot.slot_suffix", "A/B слот", False),
        ("Память", "adb shell df -h", "Свободное место на разделах", False),
        ("ОЗУ", "adb shell cat /proc/meminfo", "", False),
        ("Процессор", "adb shell cat /proc/cpuinfo", "", False),
        ("IP адрес", "adb shell ip -f inet addr show wlan0", "", False),
        ("Активное окно", "adb shell \"dumpsys window | grep mCurrentFocus\"", "Какое приложение открыто", False),
        ("Root?", "adb shell \"which su || echo no-root\"", "Проверка наличия su", False),
    ],
    "🎨 Экран и система": [
        ("Разрешение экрана", "adb shell wm size", "", False),
        ("Плотность (DPI)", "adb shell wm density", "", False),
        ("Сбросить разрешение/DPI", "adb shell wm size reset && adb shell wm density reset", "", False),
        ("Анимации 0.5x", "adb shell settings put global window_animation_scale 0.5 && adb shell settings put global transition_animation_scale 0.5 && adb shell settings put global animator_duration_scale 0.5", "Ускоряет интерфейс", False),
        ("Отключить анимации", "adb shell settings put global window_animation_scale 0 && adb shell settings put global transition_animation_scale 0 && adb shell settings put global animator_duration_scale 0", "", False),
        ("Анимации 1x", "adb shell settings put global window_animation_scale 1 && adb shell settings put global transition_animation_scale 1 && adb shell settings put global animator_duration_scale 1", "По умолчанию", False),
        ("Показывать касания", "adb shell settings put system show_touches 1", "", False),
        ("Скрыть касания", "adb shell settings put system show_touches 0", "", False),
        ("Тёмная тема", "adb shell cmd uimode night yes", "", False),
        ("Светлая тема", "adb shell cmd uimode night no", "", False),
        ("Не гасить экран (USB)", "adb shell svc power stayon usb", "", False),
        ("Гасить экран как обычно", "adb shell svc power stayon false", "", False),
    ],
    "⚡ Fastboot": [
        ("Вся информация", "fastboot getvar all", "Все переменные загрузчика", False),
        ("Статус разблокировки", "fastboot getvar unlocked", "", False),
        ("Текущий слот", "fastboot getvar current-slot", "", False),
        ("Fastbootd?", "fastboot getvar is-userspace", "yes = fastbootd", False),
        ("Можно разблокировать?", "fastboot flashing get_unlock_ability", "", False),
        ("Device info (OEM)", "fastboot oem device-info", "", False),
        ("Слот A активный", "fastboot set_active a", "", True),
        ("Слот B активный", "fastboot set_active b", "", True),
        ("Перезагрузка", "fastboot reboot", "", False),
        ("В Bootloader", "fastboot reboot bootloader", "", False),
        ("В Fastbootd", "fastboot reboot fastboot", "", False),
        ("В Recovery", "fastboot reboot recovery", "", False),
        ("Продолжить загрузку", "fastboot continue", "", False),
        ("Сброс данных (-w)", "fastboot -w", "Стирает userdata и cache!", True),
    ],
}


def all_completions() -> list[str]:
    seen: list[str] = []
    for items in PRESETS.values():
        for _t, cmd, _d, _x in items:
            if "&&" not in cmd and cmd not in seen:
                seen.append(cmd)
    extra = ["adb shell", "adb install -r ", "adb push ", "adb pull ", "adb sideload ",
             "adb logcat -d", "adb shell pm list packages -3", "fastboot flash boot ",
             "fastboot flash init_boot ", "fastboot flash vbmeta ", "fastboot boot ",
             "fastboot erase ", "fastboot flashing unlock", "fastboot flashing lock"]
    return seen + [e for e in extra if e not in seen]
