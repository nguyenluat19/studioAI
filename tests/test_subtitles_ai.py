"""Tests for the subtitle intelligence layer (app/subtitles.py)."""
import json
import shutil
import subprocess

import pytest

from app import subtitles
from app.config import settings


def test_wrap_subtitle_basic():
    assert subtitles.wrap_subtitle("short line") == "short line"


def test_wrap_subtitle_wraps_long_line():
    text = "this is a very long sentence that definitely cannot fit on one subtitle line at all"
    out = subtitles.wrap_subtitle(text, max_chars=42, max_lines=2)
    lines = out.split("\n")
    assert len(lines) <= 2
    assert all(len(l) <= 42 for l in lines)


def test_wrap_subtitle_empty():
    assert subtitles.wrap_subtitle("") == ""
    assert subtitles.wrap_subtitle(None) == ""


def test_whisper_model_for():
    assert subtitles.whisper_model_for("fast") == "small"
    assert subtitles.whisper_model_for("accurate") == "medium"
    assert subtitles.whisper_model_for("best") == "large-v3"
    assert subtitles.whisper_model_for("nonsense") == "medium"


def test_refine_transcript_fixes_text_keeps_times(monkeypatch):
    segments = [{"start": 0.0, "end": 1.0, "text": "hello wrld"},
                {"start": 1.5, "end": 3.0, "text": "this is test"}]
    calls = {}

    def fake_chat(model, messages, **kwargs):
        calls["messages"] = messages
        return {"content": json.dumps({"lines": ["hello world", "this is the test"]})}

    monkeypatch.setattr(subtitles.ai, "chat", fake_chat)
    out = subtitles.refine_transcript(segments, "m", {"api_key": "k", "model_name": "x", "base_url": "http://x"})
    assert [s["text"] for s in out] == ["hello world", "this is the test"]
    assert out[0]["start"] == 0.0 and out[1]["end"] == 3.0
    assert calls["messages"]


def test_refine_transcript_rejects_length_mismatch(monkeypatch):
    segments = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 1.0, "end": 2.0, "text": "b"}]

    def fake_chat(model, messages, **kwargs):
        return {"content": json.dumps({"lines": ["only one"]})}

    monkeypatch.setattr(subtitles.ai, "chat", fake_chat)
    assert subtitles.refine_transcript(segments, "m", {"api_key": "k", "model_name": "x"}) is None


def test_refine_transcript_no_llm_returns_none():
    assert subtitles.refine_transcript([{"start": 0.0, "end": 1.0, "text": "x"}], "m", {}) is None


def test_translate_segments_in_context(monkeypatch):
    segments = [{"start": 0.0, "end": 1.0, "text": "I love you"}]
    calls = []

    def fake_chat(model, messages, **kwargs):
        calls.append(messages)
        system = messages[0]["content"]
        user = messages[-1]["content"]
        assert "VI" in system and "câu trước" not in system
        return {"content": json.dumps({"lines": ["Tôi yêu bạn"]})}

    monkeypatch.setattr(subtitles.ai, "chat", fake_chat)
    out = subtitles.translate_segments(segments, "en", "vi", "m",
                                        {"api_key": "k", "model_name": "x", "base_url": "http://x"})
    assert out == ["Tôi yêu bạn"]
    assert calls


def test_translate_segments_batch_mismatch_falls_back_to_original(monkeypatch):
    segments = [{"start": 0.0, "end": 1.0, "text": "one"},
                {"start": 1.0, "end": 2.0, "text": "two"}]

    def fake_chat(model, messages, **kwargs):
        return {"content": json.dumps({"lines": ["một"]})}   # thiếu 1 câu

    monkeypatch.setattr(subtitles.ai, "chat", fake_chat)
    out = subtitles.translate_segments(segments, "en", "vi", "m",
                                        {"api_key": "k", "model_name": "x"})
    assert out == ["one", "two"]


def test_merge_overlapping_cues():
    segs = [{"start": 0.0, "end": 2.0, "text": "hello"},
            {"start": 1.5, "end": 3.0, "text": "world"}]
    merged = subtitles._merge(segs)
    assert len(merged) == 1
    assert merged[0]["text"] == "hello world"
    assert merged[0]["end"] == 3.0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_transcribe_endpoint_uses_ai_and_returns_metadata(client, make_user, monkeypatch):
    """Byte-level ASR/translate are mocked; the endpoint must still expose llm_used etc."""
    headers, uid = make_user()
    dest = settings.uploads_dir / f"u{uid}" / "test_subtitle_ai.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=s=64x64:d=1:r=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-shortest", str(dest)], check=True)
    try:
        def fake_asr(audio, quality="accurate", vad=True, model_override="", progress=None):
            assert model_override == ""          # không ép model khi .env trống
            return ([{"start": 0.0, "end": 0.9, "text": "hello world"}],
                    {"language": "en", "language_probability": 0.99,
                     "model": "medium", "recovered": 2})

        monkeypatch.setattr(subtitles, "transcribe_audio", fake_asr)
        monkeypatch.setattr("app.routers.videotools._resolve_llm",
                            lambda db, mid: {"id": "deepseek-llm", "name": "DeepSeek LLM",
                                             "creds": {"base_url": "http://fake",
                                                       "api_key": "k",
                                                       "model_name": "deepseek-v4-flash"},
                                             "price": 0.0})

        def fake_translate(segments, src, tgt, llm_id, creds, batch=25):
            assert tgt == "vi"
            return ["Xin chào thế giới"]

        monkeypatch.setattr(subtitles, "translate_segments", fake_translate)
        monkeypatch.setattr(subtitles, "refine_transcript",
                            lambda segments, llm_id, creds: [{**segments[0], "text": "hello world!"}])

        r = client.post("/api/video/transcribe",
                        json={"video_url": f"/media/uploads/u{uid}/test_subtitle_ai.mp4",
                              "target_lang": "vi",
                              "quality": "accurate",
                              "use_llm": True},
                        headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["asr_model"] == "medium"
        assert body["asr_recovered_cues"] == 2
        assert body["llm_used"] == "refine+translate"
        assert body["translate_status"] == "ok_llm"
        assert body["segments"][0]["translated"] == "Xin chào thế giới"
        assert "srt_translated" in body and body["srt_translated"]
    finally:
        dest.unlink(missing_ok=True)
