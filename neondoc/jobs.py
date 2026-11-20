"""Фоновые задачи. Одна за раз: GPU одна, Qwen всё равно обрабатывает запросы по очереди."""
from __future__ import annotations

import threading
import time
import traceback
import uuid


class Job:
    def __init__(self, kind: str, title: str, work_id: str | None):
        self.id = uuid.uuid4().hex[:10]
        self.kind, self.title, self.work_id = kind, title, work_id
        self.lines: list[str] = []
        self.status = "running"
        self.error: str | None = None
        self.result = None
        self.started = time.time()
        self.finished: float | None = None
        self._stop = False

    def emit(self, line: str):
        self.lines.append(f"{time.strftime('%H:%M:%S')}  {line}")
        if len(self.lines) > 500:
            self.lines = self.lines[-500:]

    def stop_requested(self) -> bool:
        return self._stop

    def as_dict(self, since: int = 0) -> dict:
        return {"id": self.id, "kind": self.kind, "title": self.title, "work_id": self.work_id,
                "status": self.status, "error": self.error, "lines": self.lines[since:],
                "total_lines": len(self.lines), "result": self.result,
                "elapsed": round((self.finished or time.time()) - self.started, 1)}


class JobManager:
    def __init__(self):
        self.current: Job | None = None
        self.history: list[Job] = []
        self._lock = threading.Lock()

    def busy(self) -> bool:
        return self.current is not None and self.current.status == "running"

    def start(self, kind: str, title: str, fn, work_id: str | None = None) -> Job:
        with self._lock:
            if self.busy():
                raise RuntimeError(f"Уже выполняется: {self.current.title}")
            job = Job(kind, title, work_id)
            self.current = job
            self.history = ([job] + self.history)[:20]

        def run():
            try:
                job.result = fn(job)
                job.status = "done"
            except Exception as e:  # noqa
                from reportgen.pipeline import Stopped
                job.status = "stopped" if isinstance(e, Stopped) else "error"
                job.error = str(e)
                job.emit(("СТОП: " if job.status == "stopped" else "ОШИБКА: ") + str(e))
                if job.status == "error" and not getattr(e, "quiet", False):
                    tb = traceback.format_exc().strip().splitlines()[-3:]
                    for t in tb:
                        job.emit("  " + t)
            finally:
                job.finished = time.time()

        threading.Thread(target=run, daemon=True).start()
        return job

    def get(self, jid: str) -> Job | None:
        return next((j for j in self.history if j.id == jid), None)

    def stop(self):
        if self.busy():
            self.current._stop = True
            self.current.emit("Остановка после текущего вызова модели…")


jobs = JobManager()
