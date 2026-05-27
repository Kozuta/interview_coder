"""Оркестрация пайплайна кодирования."""

from __future__ import annotations

import json
from pathlib import Path

from coder.config import ProjectConfig, artifacts_dir, load_config, project_path
from coder.criticality import assign_criticality, build_summary
from coder.llm import chat_json, get_client, resolve_model, unwrap_list
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
    return unwrap_list(result, "themes")


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

    raw_observations = _atomize_blocks(client, model, transcript.respondent_id, blocks)
    observations: list[Observation] = []
    for raw in raw_observations:
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


def _atomize_blocks(
    client,
    model: str,
    respondent_id: str,
    blocks: list[dict],
    chunk_size: int = 8,
) -> list[dict]:
    """Атомизация с авто-бисекцией: если LLM обрезает ответ — делим чанк пополам."""
    if not blocks:
        return []
    raw: list[dict] = []
    for start in range(0, len(blocks), chunk_size):
        chunk = blocks[start : start + chunk_size]
        raw.extend(_atomize_chunk(client, model, respondent_id, chunk))
    return raw


def _atomize_chunk(
    client,
    model: str,
    respondent_id: str,
    blocks: list[dict],
) -> list[dict]:
    if not blocks:
        return []
    try:
        result = chat_json(client, model, atomize_prompt(respondent_id, json.dumps(blocks, ensure_ascii=False)))
        return [r for r in unwrap_list(result, "observations") if isinstance(r, dict)]
    except Exception as e:
        if len(blocks) == 1:
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Пропуск атомизации реплики {blocks[0].get('utterance_index')}: {e}")
            return []
        mid = len(blocks) // 2
        print(f"[авторазбивка атомизации] {len(blocks)} → {mid}+{len(blocks)-mid}")
        return _atomize_chunk(client, model, respondent_id, blocks[:mid]) + \
               _atomize_chunk(client, model, respondent_id, blocks[mid:])


def _code_and_cluster(client, model: str, observations: list[Observation]) -> list[Observation]:
    if not observations:
        return []

    for start in range(0, len(observations), 15):
        _apply_codes_chunk(client, model, observations[start : start + 15])

    for start in range(0, len(observations), 25):
        _apply_affinity_chunk(client, model, observations[start : start + 25])

    # Нормализация: сливаем синонимичные кластеры из разных чанков в одно имя
    observations = _normalize_cluster_names(client, model, observations)

    return observations


def _apply_codes_chunk(client, model: str, chunk: list[Observation]) -> None:
    """Кодировка наблюдений in-place; при сбое рекурсивно делит чанк пополам."""
    if not chunk:
        return
    payload = [{"temp_id": i, "atom": o.atom, "quote": o.quote} for i, o in enumerate(chunk)]
    try:
        result = chat_json(client, model, code_observations_prompt(json.dumps(payload, ensure_ascii=False)))
        coded = {c["temp_id"]: c for c in unwrap_list(result, "coded") if isinstance(c, dict)}
        for i, o in enumerate(chunk):
            c = coded.get(i, {})
            o.primary_code = c.get("primary_code", "")
            o.secondary_code = c.get("secondary_code")
            o.modality_tags = c.get("modality_tags", [])
            o.kind = c.get("kind", "Наблюдение")
            o.is_key_task = bool(c.get("is_key_task", False))
    except Exception as e:
        if len(chunk) == 1:
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Пропуск кодировки наблюдения {chunk[0].id}: {e}")
            return
        mid = len(chunk) // 2
        print(f"[авторазбивка кодировки] {len(chunk)} → {mid}+{len(chunk)-mid}")
        _apply_codes_chunk(client, model, chunk[:mid])
        _apply_codes_chunk(client, model, chunk[mid:])


def _apply_affinity_chunk(client, model: str, chunk: list[Observation]) -> None:
    """Affinity-кластеризация in-place; при сбое рекурсивно делит чанк пополам."""
    if not chunk:
        return
    payload = [{"temp_id": i, "atom": o.atom} for i, o in enumerate(chunk)]
    try:
        result = chat_json(client, model, affinity_prompt(json.dumps(payload, ensure_ascii=False)))
        for item in unwrap_list(result, "clusters"):
            if not isinstance(item, dict):
                continue
            idx = item.get("temp_id")
            if idx is None or idx >= len(chunk):
                continue
            chunk[idx].affinity_cluster = item.get("affinity_cluster", "")
            chunk[idx].normalized_category = item.get("normalized_category", "")
    except Exception as e:
        if len(chunk) == 1:
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Пропуск affinity наблюдения {chunk[0].id}: {e}")
            return
        mid = len(chunk) // 2
        print(f"[авторазбивка affinity] {len(chunk)} → {mid}+{len(chunk)-mid}")
        _apply_affinity_chunk(client, model, chunk[:mid])
        _apply_affinity_chunk(client, model, chunk[mid:])


def _normalize_batch(client, model: str, clusters: list[str]) -> dict[str, str]:
    """Нормализует список кластеров; при сбое рекурсивно делит пополам."""
    if not clusters:
        return {}
    try:
        result = chat_json(client, model, normalize_clusters_prompt(json.dumps(clusters, ensure_ascii=False)))
        items = result if isinstance(result, list) else result.get("mapping", [])
        return {item["original"]: item["canonical"] for item in items if isinstance(item, dict) and item.get("canonical")}
    except Exception as e:
        if len(clusters) == 1:
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Пропуск нормализации кластера: {e}")
            return {clusters[0]: clusters[0]}
        mid = len(clusters) // 2
        print(f"[авторазбивка нормализации] {len(clusters)} → {mid}+{len(clusters)-mid}")
        left = _normalize_batch(client, model, clusters[:mid])
        right = _normalize_batch(client, model, clusters[mid:])
        return {**left, **right}


def _normalize_cluster_names(
    client,
    model: str,
    observations: list[Observation],
) -> list[Observation]:
    unique = [c for c in dict.fromkeys(o.affinity_cluster for o in observations if o.affinity_cluster)]
    if len(unique) <= 1:
        return observations

    try:
        norm_chunk = 10
        mapping: dict[str, str] = {}
        for start in range(0, len(unique), norm_chunk):
            batch = unique[start : start + norm_chunk]
            mapping.update(_normalize_batch(client, model, batch))

        # Второй проход: объединяем canonical-имена между чанками
        if len(unique) > norm_chunk:
            canonical_unique = list(dict.fromkeys(mapping.values()))
            if len(canonical_unique) > 1:
                canon_map = _normalize_batch(client, model, canonical_unique)
                mapping = {orig: canon_map.get(canon, canon) for orig, canon in mapping.items()}

        for o in observations:
            if o.affinity_cluster and o.affinity_cluster in mapping:
                o.affinity_cluster = mapping[o.affinity_cluster]
    except Exception as e:
        print(f"[ПРЕДУПРЕЖДЕНИЕ] Нормализация кластеров пропущена: {e}")

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
