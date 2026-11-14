"""Asynchronous command execution built on QProcess.

* CommandRunner — sequential job queue with live output (used for anything the
  user sees in the console: flashing, installs, reboots, ...).
* capture()     — fire-and-forget background query returning the full output
  to a callback (device polling, getprop, package lists, ...).
"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

_LINE_SPLIT = re.compile(r"\r\n|\n|\r")

# Pseudo-programs handled inside the runner (used by scripts)
SLEEP = "__sleep__"
ECHO = "__echo__"


def _quote(arg: str) -> str:
    return f'"{arg}"' if (not arg or any(c in arg for c in " \t|&;<>()")) else arg


@dataclass
class Job:
    program: str
    args: list[str] = field(default_factory=list)
    label: str = ""
    allow_fail: bool = False

    def display(self) -> str:
        if self.program == SLEEP:
            return f"sleep {self.args[0]}"
        name = Path(self.program).stem or self.program
        return " ".join([name] + [_quote(a) for a in self.args])


class CommandRunner(QObject):
    output = pyqtSignal(str, str)        # text, kind: cmd|out|err|ok|fail|info
    busyChanged = pyqtSignal(bool)
    progress = pyqtSignal(int, int)      # done, total
    queueFinished = pyqtSignal(bool)     # True if every job succeeded

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._queue: deque[Job] = deque()
        self._proc: QProcess | None = None
        self._job: Job | None = None
        self._total = 0
        self._done = 0
        self._ok = True
        self._stop_on_error = True
        self._stopped = False
        self._buf = {"out": "", "err": ""}
        self._t0 = 0.0
        self.queue_jobs: list[Job] = []   # every job of the current / last queue (for history)

    # ------------------------------------------------------------------ API
    @property
    def busy(self) -> bool:
        return self._proc is not None or bool(self._queue)

    def enqueue(self, jobs: list[Job] | Job, stop_on_error: bool = True) -> None:
        jobs = [jobs] if isinstance(jobs, Job) else list(jobs)
        if not jobs:
            return
        was_busy = self.busy
        if not was_busy:
            self._total = self._done = 0
            self._ok = True
            self._stop_on_error = stop_on_error
            self.queue_jobs = []
        self.queue_jobs.extend(jobs)
        self._queue.extend(jobs)
        self._total += len(jobs)
        self.progress.emit(self._done, self._total)
        if not was_busy:
            self.busyChanged.emit(True)
            self._next()

    def stop(self) -> None:
        if not self.busy:
            return
        self._queue.clear()
        if isinstance(self._proc, QTimer):
            self._stopped = True
            self._proc.stop()
            self._job_done(self._proc, -1)
        elif self._proc is not None:
            self._stopped = True
            self._proc.kill()
        self.output.emit("⏹ Остановлено пользователем", "info")

    # ------------------------------------------------------------ internals
    def _next(self) -> None:
        if not self._queue:
            self._finish_queue()
            return
        job = self._queue.popleft()
        self._job = job
        self._stopped = False
        self._buf = {"out": "", "err": ""}
        if job.program == ECHO:
            self.output.emit(" ".join(job.args), "info")
            self._done += 1
            self.progress.emit(self._done, self._total)
            self._job = None
            QTimer.singleShot(0, self._next)
            return
        if job.program == SLEEP:
            self.output.emit(f"❯ {job.display()}", "cmd")
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda t=timer: self._job_done(t, 0) if t is self._proc else None)
            self._proc = timer
            self._t0 = time.monotonic()
            try:
                timer.start(int(float(job.args[0]) * 1000))
            except (ValueError, IndexError):
                self.output.emit("✖ sleep: укажите число секунд", "fail")
                timer.start(0)
            return
        proc = QProcess(self)
        proc.readyReadStandardOutput.connect(lambda p=proc: self._read(p, "out"))
        proc.readyReadStandardError.connect(lambda p=proc: self._read(p, "err"))
        proc.finished.connect(lambda code, status, p=proc: self._on_finished(p, code, status))
        proc.errorOccurred.connect(lambda err, p=proc: self._on_error(p, err))
        self._proc = proc
        if job.label:
            self.output.emit(f"▸ {job.label}", "info")
        self.output.emit(f"❯ {job.display()}", "cmd")
        self._t0 = time.monotonic()
        proc.start(job.program, job.args)

    def _read(self, proc: QProcess, kind: str) -> None:
        raw = proc.readAllStandardOutput() if kind == "out" else proc.readAllStandardError()
        text = self._buf[kind] + bytes(raw).decode("utf-8", errors="replace")
        parts = _LINE_SPLIT.split(text)
        self._buf[kind] = parts.pop()
        for line in parts:
            if line.strip():
                self.output.emit(line, kind)

    def _flush(self) -> None:
        for kind in ("out", "err"):
            if self._buf[kind].strip():
                self.output.emit(self._buf[kind], kind)
            self._buf[kind] = ""

    def _on_error(self, proc: QProcess, err: QProcess.ProcessError) -> None:
        if proc is not self._proc:
            return
        if err == QProcess.ProcessError.FailedToStart:
            self.output.emit(
                f"✖ Не удалось запустить «{self._job.program}». Проверьте путь в Настройках "
                "или скачайте platform-tools.", "fail")
            self._job_done(proc, -1)

    def _on_finished(self, proc: QProcess, code: int, status: QProcess.ExitStatus) -> None:
        if proc is not self._proc:
            return
        self._read(proc, "out")
        self._read(proc, "err")
        self._flush()
        if status == QProcess.ExitStatus.CrashExit and code == 0:
            code = -1
        self._job_done(proc, code)

    def _job_done(self, proc, code: int) -> None:
        job = self._job
        elapsed = time.monotonic() - self._t0
        self._done += 1
        if code == 0:
            self.output.emit(f"✔ OK · {elapsed:.1f} с", "ok")
        elif not self._stopped:
            self.output.emit(f"✖ Ошибка (код {code}) · {elapsed:.1f} с", "fail")
        self.progress.emit(self._done, self._total)
        if code != 0 and not (job and job.allow_fail):
            self._ok = False
            if self._stop_on_error and self._queue:
                self.output.emit(f"⚠ Очередь прервана, пропущено команд: {len(self._queue)}", "fail")
                self._queue.clear()
        self._proc = None
        self._job = None
        proc.deleteLater()
        QTimer.singleShot(0, self._next)

    def _finish_queue(self) -> None:
        if self._total > 1:
            if self._ok:
                self.output.emit(f"🎉 Все команды выполнены ({self._done}/{self._total})", "ok")
            else:
                self.output.emit(f"Выполнено {self._done}/{self._total}, были ошибки", "fail")
        self.busyChanged.emit(False)
        self.queueFinished.emit(self._ok)


# ---------------------------------------------------------------- capture()
_live: set[QProcess] = set()


def capture(program: str, args: list[str], callback: Callable[[int, object], None],
            merge: bool = True, raw: bool = False, timeout: int = 20000) -> QProcess:
    """Run a command in the background and pass (exit_code, output) to callback.

    exit_code is -1 if the program failed to start and -2 on timeout.
    """
    proc = QProcess()
    if merge:
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    timer = QTimer(proc)
    timer.setSingleShot(True)
    state = {"done": False}

    def finish(code: int) -> None:
        if state["done"]:
            return
        state["done"] = True
        try:
            timer.stop()
            data = bytes(proc.readAllStandardOutput())
        except RuntimeError:  # Qt object already destroyed (application is closing)
            _live.discard(proc)
            return
        out: object = data if raw else data.decode("utf-8", errors="replace")
        _live.discard(proc)
        proc.deleteLater()
        try:
            callback(code, out)
        except RuntimeError:
            pass  # receiver widget was destroyed

    def on_timeout() -> None:
        proc.kill()
        finish(-2)

    proc.finished.connect(lambda code, _st: finish(code))
    proc.errorOccurred.connect(
        lambda e: finish(-1) if e == QProcess.ProcessError.FailedToStart else None)
    timer.timeout.connect(on_timeout)
    _live.add(proc)
    proc.start(program, args)
    timer.start(timeout)
    return proc
