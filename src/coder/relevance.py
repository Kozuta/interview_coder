"""Фильтрация реплик по теме и тестовый срез."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from coder.models import (
    ParsedTranscript,
    RunMode,
    SegmentType,
    TestScopeType,
    Utterance,
)
from coder.prompts import filter_utterances_prompt

if TYPE_CHECKING:
    from coder.config import ProjectConfig
    from coder.llm import OpenAI


def apply_labels(
    transcript: ParsedTranscript,
    labels: list[dict],
    chunk_indices: set[int] | None = None,
) -> None:
    by_index = {item["index"]: item for item in labels}
    for u in transcript.utterances:
        if chunk_indices is not None and u.index not in chunk_indices:
            continue  # не трогаем реплики из других чанков
        lab = by_index.get(u.index)
        if not lab:
            u.segment_type = SegmentType.OFF_TOPIC
            u.include_in_coding = False
            u.exclude_reason = "не размечено"
            continue
        u.segment_type = SegmentType(lab.get("segment_type", "off_topic"))
        u.include_in_coding = bool(lab.get("include_in_coding", False))
        u.exclude_reason = lab.get("exclude_reason")


def filter_transcript_llm(
    client: "OpenAI",
    model: str,
    config: "ProjectConfig",
    transcript: ParsedTranscript,
    chunk_size: int = 15,
) -> ParsedTranscript:
    for start in range(0, len(transcript.utterances), chunk_size):
        chunk = transcript.utterances[start : start + chunk_size]
        _filter_chunk(client, model, config, transcript, chunk)

    for u in transcript.utterances:
        if u.segment_type != SegmentType.ON_TOPIC:
            u.include_in_coding = False
        elif u.is_respondent:
            u.include_in_coding = True
        else:
            u.include_in_coding = False

    return transcript


def _filter_chunk(
    client: "OpenAI",
    model: str,
    config: "ProjectConfig",
    transcript: ParsedTranscript,
    chunk: list[Utterance],
) -> None:
    """Фильтрация чанка реплик; при сбое рекурсивно делит пополам."""
    from coder.llm import chat_json, unwrap_list

    if not chunk:
        return
    chunk_indices = {u.index for u in chunk}
    payload = [
        {
            "index": u.index,
            "speaker": u.speaker,
            "is_respondent": u.is_respondent,
            "text": u.text[:500],
        }
        for u in chunk
    ]
    prompt = filter_utterances_prompt(
        config.research_topic,
        config.related_themes,
        json.dumps(payload, ensure_ascii=False),
    )
    try:
        result = chat_json(client, model, prompt)
        apply_labels(transcript, unwrap_list(result, "labels"), chunk_indices)
    except RuntimeError as e:
        if len(chunk) == 1:
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Пропуск фильтрации реплики {chunk[0].index}: {e}")
            apply_labels(
                transcript,
                [{"index": chunk[0].index, "segment_type": "on_topic",
                  "include_in_coding": chunk[0].is_respondent, "exclude_reason": None}],
                chunk_indices,
            )
            return
        mid = len(chunk) // 2
        print(f"[авторазбивка фильтра] {len(chunk)} → {mid}+{len(chunk)-mid}")
        _filter_chunk(client, model, config, transcript, chunk[:mid])
        _filter_chunk(client, model, config, transcript, chunk[mid:])


def select_transcripts_for_run(
    transcripts: list[ParsedTranscript],
    run_mode: RunMode,
) -> list[ParsedTranscript]:
    if run_mode.value == "test":
        return transcripts[:1]
    return transcripts


def apply_test_scope(
    transcript: ParsedTranscript,
    config: "ProjectConfig",
) -> ParsedTranscript:
    on_topic = [
        u
        for u in transcript.utterances
        if u.segment_type == SegmentType.ON_TOPIC and u.include_in_coding
    ]
    if not on_topic:
        return transcript

    scope = config.test_scope
    selected: set[int] = set()

    if scope.type == TestScopeType.DURATION_MINUTES:
        start_sec = on_topic[0].timestamp_sec or 0
        limit = start_sec + scope.value * 60
        for u in on_topic:
            if (u.timestamp_sec or 0) <= limit:
                selected.add(u.index)
    else:
        respondent_on_topic = [u for u in on_topic if u.is_respondent]
        for u in respondent_on_topic[: scope.value]:
            selected.add(u.index)
        for u in on_topic:
            if u.index in selected:
                continue
            if any(abs((u.timestamp_sec or 0) - (x.timestamp_sec or 0)) < 120 for x in respondent_on_topic if x.index in selected):
                selected.add(u.index)

    for u in transcript.utterances:
        if u.index not in selected and u.segment_type == SegmentType.ON_TOPIC:
            u.include_in_coding = False
            u.exclude_reason = (u.exclude_reason or "") + "; вне тестового среза"

    return transcript


def filter_stats(transcript: ParsedTranscript) -> dict:
    total = len(transcript.utterances)
    excluded = sum(1 for u in transcript.utterances if not u.include_in_coding)
    on_topic = sum(1 for u in transcript.utterances if u.segment_type == SegmentType.ON_TOPIC)
    return {
        "total": total,
        "excluded": excluded,
        "on_topic": on_topic,
        "coding": sum(1 for u in transcript.utterances if u.include_in_coding and u.is_respondent),
    }
