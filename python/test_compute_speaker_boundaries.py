"""Unit tests for _compute_speaker_boundaries (the standalone BND job).

The boundaries job is the fast lane: forced alignment only — no Whisper,
no IPA — written to ``tiers.ortho_words``. These tests stub
``ai.forced_align.align_segments`` so they stay hermetic (no torch, no
real model) and verify:

  - dispatch through ``_run_compute_job`` for ``"boundaries"`` and aliases
  - missing STT cache produces a clear error
  - manuallyAdjusted=True intervals survive a re-run by default
  - aligned words overlapping a manual interval are dropped
  - overwrite=True discards even manual edits
  - generated intervals always carry manuallyAdjusted=False
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


def _seed_annotation(tmp_path, speaker, ortho_words=None, source_audio="raw/Fail02.wav"):
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    tiers = {
        "ipa":     {"type": "interval", "display_order": 1, "intervals": []},
        "ortho":   {"type": "interval", "display_order": 2, "intervals": []},
        "concept": {"type": "interval", "display_order": 3, "intervals": []},
        "speaker": {"type": "interval", "display_order": 4, "intervals": []},
    }
    if ortho_words is not None:
        tiers["ortho_words"] = {
            "type": "interval", "display_order": 5, "intervals": ortho_words,
        }
    annotation = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": 10.0,
        "tiers": tiers,
        "metadata": {
            "language_code": "sdh",
            "created": "2026-01-01T00:00:00Z",
            "modified": "2026-01-01T00:00:00Z",
        },
    }
    (annotations_dir / f"{speaker}.parse.json").write_text(
        json.dumps(annotation), encoding="utf-8",
    )
    return annotation


def _write_fake_source_wav(tmp_path, rel_path):
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    return path


def _write_stt_cache(tmp_path, speaker, segments):
    """Drop a coarse_transcripts/<speaker>.json so _read_stt_cache finds it."""
    cache_dir = tmp_path / "coarse_transcripts"
    cache_dir.mkdir(exist_ok=True)
    payload = {
        "speaker": speaker,
        "source_wav": "raw/{0}.wav".format(speaker),
        "language": "ku",
        "segments": segments,
    }
    (cache_dir / f"{speaker}.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )


def _load_canonical(tmp_path, speaker):
    return json.loads((tmp_path / "annotations" / f"{speaker}.parse.json").read_text("utf-8"))


def _install_align_stub(monkeypatch, fake_aligned):
    """Stub ai.forced_align.align_segments to return a fixed result."""
    import ai.forced_align as fa

    def _fake(audio_path, segments, **kwargs):
        return fake_aligned

    monkeypatch.setattr(fa, "align_segments", _fake)


# ---------------------------------------------------------------------------
# Happy-path: empty ortho_words -> populated from forced alignment
# ---------------------------------------------------------------------------

def test_writes_ortho_words_from_stt_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    segments = [
        {
            "start": 0.0, "end": 2.0, "text": "بەش سەرە",
            "words": [
                {"word": "بەش", "start": 0.05, "end": 0.55, "prob": 0.95},
                {"word": "سەرە", "start": 0.60, "end": 1.20, "prob": 0.90},
            ],
        },
    ]
    aligned = [[
        {"word": "بەش", "start": 0.08, "end": 0.52, "confidence": 0.97,
         "method": "wav2vec2"},
        {"word": "سەرە", "start": 0.62, "end": 1.18, "confidence": 0.93,
         "method": "wav2vec2"},
    ]]
    _install_align_stub(monkeypatch, aligned)

    _seed_annotation(tmp_path, "Fail02")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_stt_cache(tmp_path, "Fail02", segments)

    result = server._compute_speaker_boundaries("j1", {"speaker": "Fail02"})
    assert result["generated"] == 2
    assert result["preserved_manual"] == 0
    assert result["total"] == 2

    ann = _load_canonical(tmp_path, "Fail02")
    words = ann["tiers"]["ortho_words"]["intervals"]
    assert [iv["text"] for iv in words] == ["بەش", "سەرە"]
    assert words[0]["start"] == pytest.approx(0.08)
    assert words[0]["end"] == pytest.approx(0.52)
    assert words[0]["source"] == "forced_align"
    # Generated intervals must carry manuallyAdjusted=False — the on-disk
    # contract requires the flag to be present (not absent) so downstream
    # code can branch unambiguously.
    assert words[0]["manuallyAdjusted"] is False
    assert words[1]["manuallyAdjusted"] is False


# ---------------------------------------------------------------------------
# Error: no STT cache -> raise with a guidance message the UI can show
# ---------------------------------------------------------------------------

def test_raises_when_no_stt_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    _seed_annotation(tmp_path, "Fail02")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    # No coarse_transcripts/Fail02.json on disk

    with pytest.raises(RuntimeError, match="Run STT first"):
        server._compute_speaker_boundaries("j1", {"speaker": "Fail02"})


def test_raises_when_stt_cache_has_no_word_timestamps(tmp_path, monkeypatch):
    """Whisper without word_timestamps=True caches segments with no
    words[]; forced alignment can't seed off that, so we error early
    instead of silently returning an empty BND."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    segments = [{"start": 0.0, "end": 2.0, "text": "no words here"}]
    _seed_annotation(tmp_path, "Fail02")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_stt_cache(tmp_path, "Fail02", segments)

    with pytest.raises(RuntimeError, match="Run STT first"):
        server._compute_speaker_boundaries("j1", {"speaker": "Fail02"})


# ---------------------------------------------------------------------------
# manuallyAdjusted preservation
# ---------------------------------------------------------------------------

def test_preserves_manually_adjusted_intervals(tmp_path, monkeypatch):
    """A re-run must keep `manuallyAdjusted=True` intervals verbatim and
    drop any aligned word that would overlap them — manual edits anchor
    their slice of the timeline."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    segments = [
        {
            "start": 0.0, "end": 2.0, "text": "a b c",
            "words": [
                {"word": "a", "start": 0.0, "end": 0.5, "prob": 0.9},
                {"word": "b", "start": 0.5, "end": 1.0, "prob": 0.9},
                {"word": "c", "start": 1.0, "end": 1.5, "prob": 0.9},
            ],
        },
    ]
    # Aligner returns fresh boundaries for all three words; only "b"
    # overlaps the user's manual interval at 0.45-1.05 and must be
    # dropped. "a" ends before 0.45, "c" starts after 1.05.
    aligned = [[
        {"word": "a", "start": 0.02, "end": 0.40, "confidence": 0.95},
        {"word": "b", "start": 0.50, "end": 0.95, "confidence": 0.92},
        {"word": "c", "start": 1.10, "end": 1.45, "confidence": 0.93},
    ]]
    _install_align_stub(monkeypatch, aligned)

    manual = [
        {"start": 0.45, "end": 1.05, "text": "user-edited",
         "manuallyAdjusted": True},
    ]
    _seed_annotation(tmp_path, "Fail02", ortho_words=manual)
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_stt_cache(tmp_path, "Fail02", segments)

    result = server._compute_speaker_boundaries("j1", {"speaker": "Fail02"})
    assert result["preserved_manual"] == 1
    assert result["generated"] == 2  # "a" and "c" — "b" dropped (overlap)
    assert result["total"] == 3

    ann = _load_canonical(tmp_path, "Fail02")
    words = ann["tiers"]["ortho_words"]["intervals"]
    by_text = {iv["text"]: iv for iv in words}
    assert by_text["user-edited"]["manuallyAdjusted"] is True
    assert by_text["user-edited"]["start"] == pytest.approx(0.45)
    assert by_text["a"]["manuallyAdjusted"] is False
    assert by_text["c"]["manuallyAdjusted"] is False
    assert "b" not in by_text  # overlap with manual interval -> dropped


def test_overwrite_true_discards_manual_intervals(tmp_path, monkeypatch):
    """Explicit overwrite=True is the escape hatch — it ignores the
    manuallyAdjusted flag and rebuilds the entire BND lane from the
    aligner output."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    segments = [
        {
            "start": 0.0, "end": 2.0, "text": "a",
            "words": [{"word": "a", "start": 0.0, "end": 0.5, "prob": 0.9}],
        },
    ]
    aligned = [[
        {"word": "a", "start": 0.02, "end": 0.45, "confidence": 0.95},
    ]]
    _install_align_stub(monkeypatch, aligned)

    manual = [
        {"start": 0.4, "end": 1.1, "text": "user-edited",
         "manuallyAdjusted": True},
    ]
    _seed_annotation(tmp_path, "Fail02", ortho_words=manual)
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_stt_cache(tmp_path, "Fail02", segments)

    result = server._compute_speaker_boundaries(
        "j1", {"speaker": "Fail02", "overwrite": True},
    )
    assert result["preserved_manual"] == 0
    assert result["generated"] == 1
    assert result["total"] == 1

    ann = _load_canonical(tmp_path, "Fail02")
    words = ann["tiers"]["ortho_words"]["intervals"]
    assert [iv["text"] for iv in words] == ["a"]
    assert words[0]["manuallyAdjusted"] is False


# ---------------------------------------------------------------------------
# Dispatch routing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("alias", ["boundaries", "bnd", "ortho_words", "ortho-words"])
def test_run_compute_job_dispatches_boundaries(tmp_path, monkeypatch, alias):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    segments = [
        {
            "start": 0.0, "end": 1.0, "text": "a",
            "words": [{"word": "a", "start": 0.0, "end": 0.5, "prob": 0.9}],
        },
    ]
    aligned = [[{"word": "a", "start": 0.0, "end": 0.5, "confidence": 0.9}]]
    _install_align_stub(monkeypatch, aligned)

    speaker = "Disp_{0}".format(alias.replace("-", "_"))
    _seed_annotation(tmp_path, speaker, source_audio="raw/{0}.wav".format(speaker))
    _write_fake_source_wav(tmp_path, "raw/{0}.wav".format(speaker))
    _write_stt_cache(tmp_path, speaker, segments)

    captured: dict = {}

    def fake_complete(job_id, result, **kwargs):
        captured["result"] = result

    def fake_error(job_id, err):
        captured["error"] = err

    monkeypatch.setattr(server, "_set_job_complete", fake_complete)
    monkeypatch.setattr(server, "_set_job_error", fake_error)

    server._run_compute_job("j-{0}".format(alias), alias, {"speaker": speaker})
    assert "error" not in captured, captured
    assert captured["result"]["generated"] == 1
