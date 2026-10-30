"""重い処理をGUIスレッド外で実行する。コールバックは必ずGUIスレッドで呼ばれる。"""
from __future__ import annotations
from ..core.i18n import tr
import itertools
import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = logging.getLogger("polaris.worker")


class _Sig(QObject):
    finished = Signal(int, bool, object)


class _Task(QRunnable):
    def __init__(self, tid, fn, args, kwargs):
        super().__init__()
        self.setAutoDelete(False)
        self.tid, self.fn, self.args, self.kwargs = tid, fn, args, kwargs
        self.sig = _Sig()

    def run(self):
        try:
            res, ok = self.fn(*self.args, **self.kwargs), True
        except Exception as e:  # noqa  ワーカー内の例外でアプリを落とさない
            (log.warning if isinstance(e, (ValueError, OSError)) else log.exception)("worker_error: %r", e)   # 想定内の失敗は警告のみ
            res, ok = e, False
        self.sig.finished.emit(self.tid, ok, res)


class TaskRunner(QObject):
    busy_changed = Signal(bool, str)

    def __init__(self, parent=None, max_threads=4):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max_threads)
        self._ids = itertools.count(1)
        self._active: dict[int, tuple] = {}
        self._closed = False

    @property
    def active_count(self) -> int:
        return len(self._active)

    def run(self, fn, on_done=None, on_error=None, *args, label=None, **kwargs):
        if self._closed:
            return
        tid = next(self._ids)
        t = _Task(tid, fn, args, kwargs)
        t.sig.finished.connect(self._on_finished)
        label = label or tr("処理中")
        self._active[tid] = (t, on_done, on_error, label)
        self.busy_changed.emit(True, label)
        self.pool.start(t)

    @Slot(int, bool, object)
    def _on_finished(self, tid, ok, payload):
        item = self._active.pop(tid, None)
        if item is None:
            return
        _, on_done, on_error, _ = item
        try:
            if ok and on_done:
                on_done(payload)
            elif not ok and on_error:
                on_error(payload)
            elif not ok:
                log.error("未処理のワーカー例外: %s", payload)
        except Exception:  # noqa
            log.exception("callback_error")
        if not self._active:
            self.busy_changed.emit(False, "")

    def shutdown(self, timeout_ms=4000) -> bool:
        self._closed = True
        ok = self.pool.waitForDone(timeout_ms)
        self._active.clear()
        return ok
