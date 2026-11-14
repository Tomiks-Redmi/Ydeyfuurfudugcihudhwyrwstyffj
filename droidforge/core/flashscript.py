"""Parse vendor flashing scripts (Xiaomi flash_all*.bat/.sh, Pixel flash-all.sh/.bat, …) into fastboot commands.

The scripts are never executed by a shell: only their `fastboot …` lines are extracted, cleaned of shell
syntax and turned into argument lists with file paths resolved against the firmware folder.
"""
from __future__ import annotations

import glob
import re
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_GLOBS = ("flash_all*.bat", "flash_all*.sh", "flash-all*.bat", "flash-all*.sh", "flash*.bat", "flash*.sh")
_CUT = re.compile(r"\s(?:\|\||&&|\||>>?|2>&1|1>&2|2>|1>)(?:\s|$)")
_FILE_CMDS = {"flash", "boot", "update", "flash:raw"}
_PRODUCT = re.compile(r"product:\s*\*?\s*\^?([A-Za-z0-9_\-|]+)")
_SCRIPT_DIR = re.compile(r'"?`dirname\s+"?\$0"?`"?/?|"?\$\(dirname\s+"?\$0"?\)"?/?|%~dp0')
_FASTBOOT = re.compile(r'(?:^|[\s@&|;("\'])fastboot(?:\.exe)?(?=\s)', re.IGNORECASE)
_SKIP_ARGS = {"--version", "devices", "help"}


@dataclass
class FlashScript:
    path: Path
    commands: list[list[str]] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def wipes_data(self) -> bool:
        return any("-w" in c or (len(c) > 1 and c[0] in ("erase", "format", "flash") and c[1].startswith("userdata"))
                   for c in self.commands)

    @property
    def locks_bootloader(self) -> bool:
        return any(c[:2] in (["flashing", "lock"], ["oem", "lock"]) for c in self.commands)

    @property
    def description(self) -> str:
        n = self.name.lower()
        if "lock" in n:
            return "прошивка + БЛОКИРОВКА загрузчика"
        if "except_storage" in n or "except_data" in n:
            return "прошивка без удаления данных"
        return "полная прошивка (с удалением данных)" if self.wipes_data else "прошивка"


def _clean_token(tok: str, root: Path) -> str | None:
    tok = tok.strip().strip('"').strip("'")
    if tok in ("%*", "$*", "$@", "%1", "$1", "${@}", "$ARGS", "%ARGS%") or not tok:
        return None
    for prefix in ("%~dp0", "$(dirname $0)/", "$(dirname \"$0\")/", "`dirname $0`/", "$DIR/", "${DIR}/", "./"):
        if tok.startswith(prefix):
            tok = tok[len(prefix):]
    return tok.replace("\\", "/")


def parse_script(path: str | Path) -> FlashScript:
    path = Path(path)
    root = path.parent
    script = FlashScript(path)
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return script
    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if not line or low.startswith(("rem ", "::", "#", "echo", "@echo")):
            continue
        pause = re.match(r"^(?:sleep|timeout(?:\s+/t)?)\s+(\d+)|^ping\s+.*-n\s+(\d+)", low)
        if pause and script.commands:
            script.commands.append(["__sleep__", pause.group(1) or pause.group(2)])
            continue
        m_fb = _FASTBOOT.search(line)
        if not m_fb:
            continue
        line = _SCRIPT_DIR.sub("", line)
        m_fb = _FASTBOOT.search(line)
        low = line.lower()
        if "getvar" in low:
            if "product" in low:
                m = _PRODUCT.search(line)
                if m:
                    script.products += [p for p in m.group(1).split("|") if p]
            continue
        rest = line[m_fb.end():]
        rest = _CUT.split(" " + rest + " ")[0]
        tokens = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', rest)
        args: list[str] = []
        skip_next = False
        for tok in tokens:
            if skip_next:
                skip_next = False
                continue
            if tok == "-s":
                skip_next = True
                continue
            cleaned = _clean_token(tok, root)
            if cleaned is not None:
                args.append(cleaned)
        if not args or args[0].startswith(("%", "$")) or args[0] in _SKIP_ARGS:
            continue
        # resolve the image argument of file commands
        verb_idx = next((i for i, a in enumerate(args) if a in _FILE_CMDS), None)
        if verb_idx is not None and len(args) > verb_idx + 1:
            file_arg = args[-1]
            if not file_arg.startswith("-") and ("." in Path(file_arg).name or "/" in file_arg):
                candidate = root / file_arg
                matches = sorted(glob.glob(str(candidate))) if any(c in file_arg for c in "*?[") else []
                resolved = Path(matches[-1]) if matches else candidate
                if not resolved.exists():
                    script.missing.append(file_arg)
                args[-1] = str(resolved)
        script.commands.append(args)
    return script


def find_scripts(folder: str | Path) -> list[FlashScript]:
    root = Path(folder)
    seen: dict[Path, FlashScript] = {}
    for pattern in SCRIPT_GLOBS:
        for p in sorted(root.glob(pattern)):
            if p not in seen:
                sc = parse_script(p)
                if sc.commands:
                    seen[p] = sc
    return list(seen.values())
