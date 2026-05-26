"""Экспорт результатов в Excel."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from coder.config import ProjectConfig, output_xlsx_path, project_path
from coder.models import Observation, ParsedTranscript, SummaryRow
from coder.prompts import MODALITY_TAGS, PRIMARY_CODES

HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _sheet_headers(ws, headers: list[str]) -> None:
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"


def _autosize(ws) -> None:
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        max_len = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[letter].width = min(max_len + 2, 60)


def export_workbook(
    project_dir: Path,
    config: ProjectConfig,
    transcripts: list[ParsedTranscript],
    observations: list[Observation],
    summary: list[SummaryRow],
) -> Path:
    wb = Workbook()
    wb.remove(wb.active)

    # Настройки
    ws = wb.create_sheet("Настройки")
    rows = [
        ("Тема", config.research_topic),
        ("Цели", config.research_goals),
        ("Режим", config.run_mode.value),
        ("Респондент (speaker)", config.respondent_speaker),
    ]
    for h in config.hypotheses:
        rows.append(("Гипотеза", h))
    for q in config.research_questions:
        rows.append(("Вопрос", q))
    for t in config.related_themes:
        rows.append(("Связанная тема", t))
    for r in rows:
        ws.append(list(r))

    # Респонденты
    ws = wb.create_sheet("Респонденты")
    field_keys = [f.key for f in config.respondent_fields]
    headers = ["ID", "Файл", "Дата", *field_keys]
    _sheet_headers(ws, headers)
    for r in config.respondents:
        meta = {"segment": r.segment, "interview_date": r.interview_date}
        meta.update(r.extra)
        row = [r.id, r.transcript_file, r.interview_date]
        row.extend(meta.get(k, "") or "" for k in field_keys)
        ws.append(row)
    _autosize(ws)

    # Кодировка
    ws = wb.create_sheet("Кодировка")
    resp_field_labels = [f.label for f in config.respondent_fields]
    resp_field_keys = [f.key for f in config.respondent_fields]
    headers = [
        "ID",
        "Респондент",
        *resp_field_labels,
        "Цитата респондента",
        "Фрагмент интервью",
        "Наблюдение",
        "Контекст",
        "Следствие",
        "Тип",
        "Кластер",
        "Категория",
        "Код",
        "Код 2",
        "Модальность",
        "Дата",
        "Содержание",
        "Ключ. задача",
    ]
    _sheet_headers(ws, headers)
    for o in sorted(observations, key=lambda x: (x.respondent_id, x.utterance_index or 0)):
        resp_values = [str(o.respondent_meta.get(k, "") or "") for k in resp_field_keys]
        ws.append(
            [
                o.id,
                o.respondent_id,
                *resp_values,
                o.quote,
                o.interview_fragment,
                o.atom,
                o.context,
                o.consequence or "-",
                o.kind,
                o.affinity_cluster,
                o.normalized_category,
                o.primary_code,
                o.secondary_code or "",
                ", ".join(o.modality_tags),
                str(o.respondent_meta.get("interview_date", "") or ""),
                o.content,
                "Да" if o.is_key_task else "Нет",
            ]
        )
    _autosize(ws)

    # Исключено
    ws = wb.create_sheet("Исключено")
    _sheet_headers(ws, ["Респондент", "Индекс", "Спикер", "Время", "Тип", "Причина", "Текст"])
    for tr in transcripts:
        for u in tr.utterances:
            if u.include_in_coding:
                continue
            ws.append(
                [
                    tr.respondent_id,
                    u.index,
                    u.speaker,
                    u.timestamp_raw,
                    u.segment_type.value if u.segment_type else "",
                    u.exclude_reason,
                    u.text[:500],
                ]
            )
    _autosize(ws)

    # Транскрипты
    ws = wb.create_sheet("Транскрипты")
    _sheet_headers(ws, ["Респондент", "Время", "Спикер", "В кодировке", "Текст", "ID наблюдений"])
    obs_by_utt: dict[tuple[str, int], list[str]] = {}
    for o in observations:
        if o.utterance_index is not None:
            obs_by_utt.setdefault((o.respondent_id, o.utterance_index), []).append(o.id)
    for tr in transcripts:
        for u in tr.utterances:
            ids = ", ".join(obs_by_utt.get((tr.respondent_id, u.index), []))
            ws.append(
                [
                    tr.respondent_id,
                    u.timestamp_raw,
                    u.speaker,
                    "Да" if u.include_in_coding else "Нет",
                    u.text[:800],
                    ids,
                ]
            )
    _autosize(ws)

    # Сводная
    ws = wb.create_sheet("Сводная")
    _sheet_headers(
        ws,
        [
            "Кластер", "Категория", "Описание",
            "Кол-во респондентов", "Частота",
            "Код", "Код 2", "Сегменты", "Критичность", "ID наблюдений",
        ],
    )
    for s in summary:
        ws.append(
            [
                s.affinity_cluster,
                s.normalized_category,
                s.description,
                s.respondent_count,
                s.cluster_frequency,
                s.primary_code,
                s.secondary_codes,
                s.segments,
                s.criticality,
                ", ".join(s.observation_ids),
            ]
        )
    _autosize(ws)

    if config.run_mode.value == "test":
        ws = wb.create_sheet("Тест")
        ws.append(["Тестовый прогон", f"scope: {config.test_scope.type.value} = {config.test_scope.value}"])
        ws.append(["Наблюдений", len(observations)])

    # Справочник
    ws = wb.create_sheet("Справочник")
    ws.append(["Коды"])
    for c in PRIMARY_CODES:
        ws.append([c])
    ws.append([])
    ws.append(["Модальности"])
    for m in MODALITY_TAGS:
        ws.append([m])

    path = output_xlsx_path(project_path(project_dir), config)
    wb.save(path)
    return path
