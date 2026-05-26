"""Оркестрация пайплайна кодирования."""

from __future__ import annotations

import json
from pathlib import Path

from coder.config import ProjectConfig, artifacts_dir, load_config, project_path
from coder.criticality import assign_criticality, build_summary
from coder.llm import chat_json, get_client, resolve_model
from coder.models import Observation, ParsedTranscript, RunMode, SegmentType
from coder.prompts import (
    affinity_prompt,
    atomize_prompt,
    code_observations_prompt,
    normalize_clusters_prompt,
    related_themes_prompt,
)
from coder.relevance import (
    apply_test_scope,
    filter_transcript_llm,
    select_transcripts_for_run,
)
from coder.transcript import load_project_transcripts


def suggest_related_themes(config: ProjectConfig) -> list[str]:
    client = get_client()
    prompt = related_themes_prompt(
        config.research_topic,
        config.hypotheses,
        config.research_questions,
    )
    result = chat_json(client, resolve_model(config.llm_model), prompt)
    return result.get("themes", [])


def _respondent_meta(config: ProjectConfig, respondent_id: str) -> dict:
    for r in config.respondents:
        if r.id == respondent_id:
            meta = {"segment": r.segment, "interview_date": r.interview_date}
            meta.update(r.extra)
            return meta
    return {}


_TRIVIAL_RESPONSES = frozenset({
    "да", "нет", "ага", "угу", "ладно", "хорошо", "окей", "ок",
    "поняла", "понял", "понятно", "конечно", "именно", "верно",
    "правильно", "точно", "именно так", "да-да", "нет-нет",
})


def _is_trivial(text: str) -> bool:
    cleaned = text.strip().rstrip(".,!?").lower()
    if len(cleaned) < 15:
        return True
    words = set(cleaned.split())
    return words <= _TRIVIAL_RESPONSES


def _build_coding_blocks(transcript: ParsedTranscript) -> list[dict]:
    blocks = []
    for u in transcript.utterances:
        if not (u.include_in_coding and u.is_respondent):
            continue
        if _is_trivial(u.text):
            continue
        ctx = _context_before(transcript, u.index)
        blocks.append(
            {
                "utterance_index": u.index,
                "text": u.text,
                "context_hint": ctx,
            }
        )
    return blocks


def _context_before(transcript: ParsedTranscript, index: int, n: int = 5) -> str:
    prior = [u for u in transcript.utterances if u.index < index][-n:]
    return " | ".join(f"{p.speaker}: {p.text[:400]}" for p in prior)


def _interview_fragment(transcript: ParsedTranscript, utt_index: int, n: int = 1) -> str:
    """Verbatim passage: N prior utterances + current utterance with timestamps."""
    current = next((u for u in transcript.utterances if u.index == utt_index), None)
    if current is None:
        return ""
    prior = [u for u in transcript.utterances if u.index < utt_index][-n:]
    parts = []
    for u in prior:
        ts = u.timestamp_raw or ""
        parts.append(f"{ts}\n{u.speaker}\n{u.text}")
    ts = current.timestamp_raw or ""
    parts.append(f"{ts}\n{current.speaker}\n{current.text}")
    return "\n\n".join(parts)


def _atomize(
    client,
    model: str,
    config: ProjectConfig,
    transcript: ParsedTranscript,
    obs_counter: list[int],
) -> list[Observation]:
    blocks = _build_coding_blocks(transcript)
    if not blocks:
        respondent_utts = sum(1 for u in transcript.utterances if u.is_respondent)
        if respondent_utts == 0:
            speakers = {u.speaker for u in transcript.utterances}
            print(
                f"[ПРЕДУПРЕЖДЕНИЕ] {transcript.respondent_id}: ни одна реплика не помечена "
                f"как respondent. Спикеры в файле: {speakers}. "
                f"Проверь поле 'Спикер' в настройках."
            )
        return []

    utt_by_index = {u.index: u.text for u in transcript.utterances}

    chunk_size = 15
    observations: list[Observation] = []
    for start in range(0, len(blocks), chunk_size):
        chunk = blocks[start : start + chunk_size]
        prompt = atomize_prompt(transcript.respondent_id, json.dumps(chunk, ensure_ascii=False))
        result = chat_json(client, model, prompt)
        for raw in result.get("observations", []):
            obs_counter[0] += 1
            rid = transcript.respondent_id.replace(" ", "")
            utt_idx = raw.get("utterance_index")
            observations.append(
                Observation(
                    id=f"{rid}-O{obs_counter[0]:04d}",
                    respondent_id=transcript.respondent_id,
                    quote=utt_by_index.get(utt_idx, "") if utt_idx is not None else "",
                    atom=raw.get("atom", ""),
                    interview_fragment=_interview_fragment(transcript, utt_idx) if utt_idx is not None else "",
                    context=raw.get("context", raw.get("context_hint", "")),
                    consequence=raw.get("consequence", "-"),
                    content=raw.get("content", ""),
                    utterance_index=utt_idx,
                    respondent_meta=_respondent_meta(config, transcript.respondent_id),
                )
            )
    return observations


def _code_and_cluster(client, model: str, observations: list[Observation]) -> list[Observation]:
    if not observations:
        return []

    # Кодировка чанками по 30: quote может быть длинным, ответ растёт быстро
    code_chunk = 30
    for start in range(0, len(observations), code_chunk):
        chunk = observations[start : start + code_chunk]
        payload = [
            {"temp_id": i, "atom": o.atom, "quote": o.quote}
            for i, o in enumerate(chunk)
        ]
        code_result = chat_json(client, model, code_observations_prompt(json.dumps(payload, ensure_ascii=False)))
        coded = {c["temp_id"]: c for c in code_result.get("coded", [])}
        for i, o in enumerate(chunk):
            c = coded.get(i, {})
            o.primary_code = c.get("primary_code", "")
            o.secondary_code = c.get("secondary_code")
            o.modality_tags = c.get("modality_tags", [])
            o.kind = c.get("kind", "observation")
            o.is_key_task = bool(c.get("is_key_task", False))

    # Affinity чанками по 50: только atom, вывод компактнее
    aff_chunk = 50
    for start in range(0, len(observations), aff_chunk):
        chunk = observations[start : start + aff_chunk]
        aff_payload = [{"temp_id": i, "atom": o.atom} for i, o in enumerate(chunk)]
        aff_result = chat_json(client, model, affinity_prompt(json.dumps(aff_payload, ensure_ascii=False)))
        for item in aff_result.get("clusters", []):
            idx = item.get("temp_id")
            if idx is None or idx >= len(chunk):
                continue
            chunk[idx].affinity_cluster = item.get("affinity_cluster", "")
            chunk[idx].normalized_category = item.get("normalized_category", "")

    # Нормализация: сливаем синонимичные кластеры из разных чанков в одно имя
    observations = _normalize_cluster_names(client, model, observations)

    return observations


def _normalize_cluster_names(
    client,
    model: str,
    observations: list[Observation],
) -> list[Observation]:
    unique = [c for c in dict.fromkeys(o.affinity_cluster for o in observations if o.affinity_cluster)]
    if len(unique) <= 1:
        return observations

    result = chat_json(client, model, normalize_clusters_prompt(json.dumps(unique, ensure_ascii=False)))
    items = result if isinstance(result, list) else result.get("mapping", [])
    mapping = {item["original"]: item["canonical"] for item in items if isinstance(item, dict) and item.get("canonical")}

    for o in observations:
        if o.affinity_cluster and o.affinity_cluster in mapping:
            o.affinity_cluster = mapping[o.affinity_cluster]
    return observations


def _mark_all_respondent_utterances(transcript: ParsedTranscript) -> None:
    """Без LLM-фильтра: включаем все содержательные реплики респондента."""
    for u in transcript.utterances:
        if u.is_respondent and len(u.text.strip()) > 10:
            u.segment_type = SegmentType.ON_TOPIC
            u.include_in_coding = True
        else:
            u.segment_type = SegmentType.OFF_TOPIC
            u.include_in_coding = False


def run_pipeline(project_dir: str | Path, skip_filter: bool = False) -> dict:
    root = project_path(project_dir)
    config = load_config(root)
    client = get_client()
    model = resolve_model(config.llm_model)
    out = artifacts_dir(root)

    transcripts = load_project_transcripts(
        root,
        config.transcripts_dir,
        config.respondents,
        config.respondent_speaker,
    )
    print(f"Загружено транскриптов: {len(transcripts)} — {[tr.respondent_id for tr in transcripts]}")
    transcripts = select_transcripts_for_run(transcripts, config.run_mode)
    if config.run_mode == RunMode.TEST and len(transcripts) < len(config.respondents or [1]):
        print(f"[тест] обрабатывается только первый транскрипт: {transcripts[0].respondent_id if transcripts else '—'}")

    filtered: list[ParsedTranscript] = []
    for tr in transcripts:
        if not skip_filter and not config.skip_filter:
            tr = filter_transcript_llm(client, model, config, tr)
        else:
            _mark_all_respondent_utterances(tr)
        if config.run_mode == RunMode.TEST:
            tr = apply_test_scope(tr, config)
        filtered.append(tr)
        (out / f"filtered_{tr.respondent_id}.json").write_text(
            tr.model_dump_json(indent=2),
            encoding="utf-8",
        )

    all_observations: list[Observation] = []
    for tr in filtered:
        obs_counter = [0]  # сбрасываем на каждого респондента
        all_observations.extend(_atomize(client, model, config, tr, obs_counter))

    all_observations = _code_and_cluster(client, model, all_observations)
    cluster_crit = assign_criticality(all_observations)
    summary = build_summary(all_observations, cluster_crit)

    (out / "observations.json").write_text(
        json.dumps([o.model_dump() for o in all_observations], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "summary.json").write_text(
        json.dumps([s.model_dump() for s in summary], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    from coder.export_xlsx import export_workbook

    xlsx_path = export_workbook(root, config, filtered, all_observations, summary)

    return {
        "observations_count": len(all_observations),
        "xlsx": str(xlsx_path),
        "output_dir": str(out),
    }
