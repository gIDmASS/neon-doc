"""Голос: запись с микрофона (sounddevice) и расшифровка локальным Whisper (faster-whisper).

Запись идёт на стороне Python, а не в окне: так не нужно разрешение микрофона у WebView.
Whisper грузится при первом использовании. Сначала пробуем GPU (int8_float16, ~1 ГБ VRAM рядом с Qwen),
при ошибке CUDA — CPU int8. Модель скачивается с HuggingFace один раз (~1,6 ГБ для large-v3-turbo).
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

SAMPLE_RATE = 16000

_model = None
_model_info = {"state": "not_loaded", "device": None, "error": None}
_lock = threading.Lock()


def _add_cuda_dlls():
    """На Windows библиотеки cuBLAS/cuDNN из pip-пакетов nvidia-* нужно добавить в путь поиска DLL."""
    if sys.platform != "win32":
        return
    try:
        import nvidia  # noqa
        base = Path(nvidia.__path__[0])
        for sub in ("cublas", "cudnn", "cuda_nvrtc"):
            for d in (base / sub / "bin", base / sub / "lib"):
                if d.exists():
                    os.add_dll_directory(str(d))
                    os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def status() -> dict:
    try:
        import sounddevice  # noqa
        mic = True
    except Exception:
        mic = False
    try:
        import faster_whisper  # noqa
        fw = True
    except Exception:
        fw = mlx_available()
    return {"mic": mic, "whisper_installed": fw, **_model_info, "recording": _rec.active}


# ------------------------------------------------------------------ macOS: Whisper на MLX (Apple Silicon)

MLX_REPOS = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "base": "mlx-community/whisper-base-mlx",
}


def mlx_available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import mlx_whisper  # noqa
        return True
    except Exception:
        return False


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class MLXWhisper:
    """Обёртка над mlx-whisper с тем же интерфейсом, что у faster_whisper.WhisperModel.transcribe:
    возвращает (сегменты, info), у сегментов .start .end .text .words(.start .end .word).

    MLX привязывает загруженную модель и GPU-поток к потоку Python, в котором её загрузили
    («There is no Stream(gpu, N) in current thread»). Задачи NEON.DOC идут в разных потоках,
    поэтому вся работа с MLX выполняется в одном постоянном потоке-исполнителе."""

    _pool = None

    def __init__(self, name: str):
        self.repo = MLX_REPOS.get(name, name if "/" in name else MLX_REPOS["large-v3-turbo"])

    @classmethod
    def _executor(cls):
        if cls._pool is None:
            from concurrent.futures import ThreadPoolExecutor
            cls._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")
        return cls._pool

    def _run(self, audio, language, word_timestamps, initial_prompt):
        import mlx_whisper
        kw = dict(path_or_hf_repo=self.repo, language=language, word_timestamps=word_timestamps,
                  initial_prompt=initial_prompt, condition_on_previous_text=False, verbose=None)
        try:
            return mlx_whisper.transcribe(audio, **kw)
        except RuntimeError as e:
            if "Stream" not in str(e):
                raise
            # модель могла остаться в кэше от другого потока — сбрасываем и грузим заново здесь
            try:
                from mlx_whisper.transcribe import ModelHolder
                ModelHolder.model = None
                ModelHolder.model_path = None
            except Exception:
                pass
            return mlx_whisper.transcribe(audio, **kw)

    def transcribe(self, audio, language=None, word_timestamps=False, initial_prompt=None, **_ignored):
        if isinstance(audio, (str, Path)):
            audio = str(audio)
        else:
            import numpy as np
            audio = np.asarray(audio, dtype="float32")
        r = self._executor().submit(self._run, audio, language, word_timestamps, initial_prompt).result()
        segs = []
        for s in r.get("segments") or []:
            words = [_Obj(start=w["start"], end=w["end"], word=w["word"]) for w in s.get("words") or []]
            segs.append(_Obj(start=s["start"], end=s["end"], text=s.get("text", ""), words=words))
        return iter(segs), _Obj(language=r.get("language") or language or "?")


def get_model(model_name: str, device_pref: str = "auto"):
    global _model
    with _lock:
        if _model is not None:
            return _model
        if device_pref in ("auto", "mlx") and mlx_available():
            _model = MLXWhisper(model_name)
            _model_info.update(state="ready", device=f"mlx:{model_name}", error=None)
            return _model
        from faster_whisper import WhisperModel
        _add_cuda_dlls()
        _model_info["state"] = "loading"
        attempts = []
        if device_pref in ("auto", "cuda") and sys.platform != "darwin":
            attempts.append(("cuda", "int8_float16", model_name))
        if device_pref in ("auto", "cpu"):
            # на CPU large медленный — берём small, он вполне разборчив для диктовки
            attempts.append(("cpu", "int8", model_name if device_pref == "cpu" else "small"))
        last = None
        for dev, ctype, name in attempts:
            try:
                _model = WhisperModel(name, device=dev, compute_type=ctype)
                _model_info.update(state="ready", device=f"{dev}:{name}", error=None)
                return _model
            except Exception as e:  # нет CUDA/cuDNN — пробуем дальше
                last = e
        _model_info.update(state="error", error=str(last))
        raise RuntimeError(f"Whisper не загрузился: {last}")


def transcribe(path: Path, model_name: str, device_pref: str = "auto") -> str:
    model = get_model(model_name, device_pref)
    segments, _info = model.transcribe(str(path), language="ru", vad_filter=True, beam_size=5)
    return " ".join(s.text.strip() for s in segments).strip()


class Recorder:
    def __init__(self):
        self.active = False
        self._frames = []
        self._stream = None
        self.started = 0.0

    def start(self):
        import sounddevice as sd
        if self.active:
            return
        self._frames = []

        def cb(indata, frames, t, st):
            self._frames.append(indata.copy())
        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=cb)
        self._stream.start()
        self.active = True
        self.started = time.time()

    def stop(self) -> Path:
        import numpy as np
        import soundfile as sf
        if not self.active:
            raise RuntimeError("Запись не идёт")
        self._stream.stop()
        self._stream.close()
        self.active = False
        audio = np.concatenate(self._frames) if self._frames else np.zeros((1, 1), dtype="int16")
        out = Path(tempfile.gettempdir()) / f"neondoc_{int(time.time())}.wav"
        sf.write(str(out), audio, SAMPLE_RATE)
        return out

    def level(self) -> float:
        if not self.active or not self._frames:
            return 0.0
        import numpy as np
        a = self._frames[-1].astype("float32")
        return float(min(1.0, (np.sqrt((a ** 2).mean()) / 6000)))


_rec = Recorder()


def recorder() -> Recorder:
    return _rec
