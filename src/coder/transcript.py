"""Парсинг транскриптов формата MM:SS Speaker N текст."""

from __future__ import annotations

import re
from pathlib import Path

from coder.ingest import load_document
from coder.models import ParsedTranscript, Utterance

# 00:56 Speaker 1 текст...  Якорь ^ не даёт ловить временны́е метки внутри реплики.
UTTERANCE_RE = re.compile(
    r"^(\d{1,2}):(\d{2})\s*(Speaker\s+\d+)",
    re.UNICODE | re.IGNORECASE | re.MULTILINE,
)


def timestamp_to_sec(raw: str, minutes: str, seconds: str) -> float:
    return int(minutes) * 60 + int(seconds)


def parse_transcript_text(
    text: str,
    respondent_id: str,
    source_file: str,
    respondent_speaker: str,
) -> ParsedTranscript:
    matches = list(UTTERANCE_RE.finditer(text))
    utterances: list[Utterance] = []

    if not matches:
        return ParsedTranscript(
            respondent_id=respondent_id,
            source_file=source_file,
            utterances=[],
        )

    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        speaker = match.group(3).strip()
        ts_raw = f"{match.group(1)}:{match.group(2)}"
        ts_sec = timestamp_to_sec(ts_raw, match.group(1), match.group(2))
        utterances.append(
            Utterance(
                index=len(utterances),
                timestamp_sec=ts_sec,
                timestamp_raw=ts_raw,
                speaker=speaker,
                text=body,
                is_respondent=_speakers_match(speaker, respondent_speaker),
            )
        )

    return ParsedTranscript(
        respondent_id=respondent_id,
        source_file=source_file,
        utterances=utterances,
    )


def _speakers_match(actual: str, expected: str) -> bool:
    return actual.strip().lower() == expected.strip().lower()


def parse_transcript_file(
    path: Path,
    respondent_id: str,
    respondent_speaker: str,
) -> ParsedTranscript:
    text = load_document(path)
    return parse_transcript_text(text, respondent_id, path.name, respondent_speaker)


def load_project_transcripts(
    project_dir: Path,
    transcripts_subdir: str,
    respondents: list,
    respondent_speaker: str,
) -> list[ParsedTranscript]:
    tdir = project_dir / transcripts_subdir
    results: list[ParsedTranscript] = []
    for resp in respondents:
        fpath = tdir / resp.transcript_file
        if not fpath.exists():
            raise FileNotFoundError(f"Транскрипт не найден: {fpath}")
        results.append(
            parse_transcript_file(fpath, resp.id, respondent_speaker)
        )
    return results
