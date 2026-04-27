"""Unit tests for LocalWhisperProvider.transcribe_segments_in_memory.

This is the in-memory windowed transcribe path used by the BND-anchored
re-transcription job. The tests stub faster-whisper's WhisperModel so
they stay hermetic (no model download, no torch CUDA), and verify:

  - one model.transcribe() call per (start, end) interval
  - returned segments are offset back into the global timeline
  - per-word start/end values are also offset
  - zero-range and inverted intervals are skipped
  - vad_filter is forced off + word_timestamps forced on, regardless of
    what the provider config says, since each window is already a
    coherent utterance per the user's BND edits
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, List, Tuple

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import provider as provider_module
from ai.provider import LocalWhisperProvider


class _StubWord:
    def __init__(self, word: str, start: float, end: float, prob: float = 0.9) -> None:
        self.word = word
        self.start = start
        self.end = end
        self.probability = prob


class _StubSegment:
    def __init__(
        self,
        start: float,
        end: float,
        text: str,
        words: List[_StubWord] | None = None,
        avg_logprob: float = -0.3,
    ) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob
        if words is not None:
            self.words = words


class _StubInfo:
    def __init__(self, duration: float = 1.0) -> None:
        self.duration = duration


class _RecordingWhisperModel:
    """Records every transcribe() call. Returns a deterministic local-time
    segment so the test can assert global-time offsetting works."""

    calls: List[Dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def transcribe(
        self, audio: Any, **kwargs: Any,
    ) -> Tuple[Any, _StubInfo]:
        # Audio comes in as a numpy float32 array — record its length so
        # the test can verify the slice was the expected duration.
        n = int(np.asarray(audio).shape[0]) if audio is not None else 0
        type(self).calls.append({"length": n, **kwargs})
        # Local-time segment 0.10-0.40s with one word, mirroring what
        # faster-whisper would emit for a sub-second clip.
        seg = _StubSegment(
            start=0.10, end=0.40, text="ok",
            words=[_StubWord("ok", 0.12, 0.38, prob=0.9)],
        )
        return iter([seg]), _StubInfo()


def _make_provider(tmp_path: pathlib.Path, monkeypatch: Any) -> LocalWhisperProvider:
    _RecordingWhisperModel.calls = []
    monkeypatch.setattr(
        provider_module, "_register_cuda_dll_directories", lambda: None, raising=False,
    )
    import faster_whisper  # type: ignore
    monkeypatch.setattr(faster_whisper, "WhisperModel", _RecordingWhisperModel, raising=True)
    return LocalWhisperProvider(
        config={"stt": {"language": ""}},
        config_path=tmp_path / "ai_config.json",
    )


def test_one_model_call_per_interval(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000 * 5, dtype=np.float32)  # 5s of silence
    intervals = [(0.5, 1.0), (2.0, 2.5), (3.0, 4.0)]

    out = provider.transcribe_segments_in_memory(audio, intervals)

    assert len(_RecordingWhisperModel.calls) == 3
    # Slice lengths in samples (end-start)*16000
    assert _RecordingWhisperModel.calls[0]["length"] == int(round(0.5 * 16000))
    assert _RecordingWhisperModel.calls[1]["length"] == int(round(0.5 * 16000))
    assert _RecordingWhisperModel.calls[2]["length"] == int(round(1.0 * 16000))

    # Three input intervals → three output segments.
    assert len(out) == 3


def test_segments_offset_to_global_timeline(tmp_path, monkeypatch):
    """Stub returns local 0.10-0.40s; the third interval starts at 3.0s
    so the global segment must be 3.10-3.40s, not 0.10-0.40s."""
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000 * 5, dtype=np.float32)

    out = provider.transcribe_segments_in_memory(audio, [(3.0, 4.0)])

    assert len(out) == 1
    seg = out[0]
    assert seg["start"] == 3.10
    assert seg["end"] == 3.40
    assert seg["text"] == "ok"
    # Word-level timestamps must also be offset.
    assert "words" in seg
    assert seg["words"][0]["start"] == 3.12
    assert seg["words"][0]["end"] == 3.38


def test_skips_zero_and_inverted_intervals(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000 * 5, dtype=np.float32)
    intervals = [
        (1.0, 1.0),   # zero range — skip
        (2.0, 1.5),   # inverted — skip
        (3.0, 3.5),   # valid
    ]

    out = provider.transcribe_segments_in_memory(audio, intervals)

    assert len(_RecordingWhisperModel.calls) == 1
    assert len(out) == 1


def test_clamps_segment_end_to_interval_end(tmp_path, monkeypatch):
    """faster-whisper sometimes returns end times slightly past the clip
    length. The provider must clamp to the interval's end so the BND
    boundary is never crossed in the global timeline."""
    class _OvershootModel(_RecordingWhisperModel):
        def transcribe(self, audio, **kwargs):
            type(self).calls.append({"length": int(np.asarray(audio).shape[0]), **kwargs})
            # Local end 0.6s for a 0.5s clip — overshoot.
            seg = _StubSegment(start=0.0, end=0.6, text="x", words=[])
            return iter([seg]), _StubInfo()

    monkeypatch.setattr(
        provider_module, "_register_cuda_dll_directories", lambda: None, raising=False,
    )
    import faster_whisper  # type: ignore
    monkeypatch.setattr(faster_whisper, "WhisperModel", _OvershootModel, raising=True)
    provider = LocalWhisperProvider(config={"stt": {}}, config_path=tmp_path / "x.json")

    audio = np.zeros(16000, dtype=np.float32)  # 1s
    out = provider.transcribe_segments_in_memory(audio, [(0.0, 0.5)])

    assert len(out) == 1
    assert out[0]["end"] == 0.5  # clamped to interval.end, not 0.6


def test_kwargs_force_word_timestamps_and_disable_vad(tmp_path, monkeypatch):
    """Each BND interval is already a coherent utterance per the user's
    edit; VAD and previous-text conditioning would only second-guess
    that decision. word_timestamps must be on so the BND lane can later
    compare Tier 1 word boxes."""
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000, dtype=np.float32)
    provider.transcribe_segments_in_memory(audio, [(0.0, 0.5)], language="ku")

    assert _RecordingWhisperModel.calls[0]["word_timestamps"] is True
    assert _RecordingWhisperModel.calls[0]["vad_filter"] is False
    assert _RecordingWhisperModel.calls[0]["condition_on_previous_text"] is False
    assert _RecordingWhisperModel.calls[0]["language"] == "ku"


def test_empty_intervals_returns_empty(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000, dtype=np.float32)
    assert provider.transcribe_segments_in_memory(audio, []) == []
    assert _RecordingWhisperModel.calls == []


def test_progress_callback_fires_per_interval(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000 * 3, dtype=np.float32)
    intervals = [(0.0, 0.5), (1.0, 1.5), (2.0, 2.5)]

    progress_calls: List[Tuple[float, int]] = []

    def _on_progress(pct: float, n: int) -> None:
        progress_calls.append((pct, n))

    provider.transcribe_segments_in_memory(
        audio, intervals, progress_callback=_on_progress,
    )

    assert len(progress_calls) == 3
    assert progress_calls[-1][1] == 3
    assert abs(progress_calls[-1][0] - 100.0) < 0.01
