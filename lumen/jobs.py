"""Cancellable background work for the viewer's single worker thread."""
from __future__ import annotations

import threading
import time
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal


class JobSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    cancelled = Signal()


class JobCancelled(Exception):
    pass


class Job(QRunnable):
    """Run ``function(progress)`` off the GUI thread.

    ``progress(message)`` doubles as the cancellation point: once cancel_event is set,
    the next progress call raises JobCancelled inside the worker.
    """

    def __init__(self, function, discard_on_cancel=True):
        super().__init__()
        self.function = function
        self.signals = JobSignals()
        self.cancel_event = threading.Event()
        self.last_progress = 0.
        self.discard_on_cancel = discard_on_cancel

    def progress(self, message):
        if self.cancel_event.is_set():
            raise JobCancelled()
        now = time.monotonic()
        if now - self.last_progress >= .08:
            self.signals.progress.emit(message)
            self.last_progress = now

    @staticmethod
    def discard(result):
        """Clean up temporary folders carried by an import result nobody will use."""
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], list):
            for temporary in result[1]:
                if hasattr(temporary, "cleanup"):
                    temporary.cleanup()

    def run(self):
        try:
            result = self.function(self.progress)
            if self.cancel_event.is_set() and self.discard_on_cancel:
                self.discard(result)
                raise JobCancelled()
            self.signals.finished.emit(result)
        except JobCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            traceback.print_exc()
            self.signals.failed.emit(str(exc))
