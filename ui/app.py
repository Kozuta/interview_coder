"""Streamlit UI кодировщика интервью."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "src"))

from coder.config import artifacts_dir, load_config, project_path, save_config  # noqa: E402
from coder.models import (  # noqa: E402
    RespondentField,
    RespondentMeta,
    RunMode,
    TestScope,
    TestScopeType,
)
from coder.pipeline import run_pipeline, suggest_related_themes  # noqa: E402
from coder.transcript import parse_transcript_file  # noqa: E402

st.set_page_config(page_title="Кодировщик интервью", layout="wide")
st.title("Кодировщик интервью")

project_dir = st.text_input(
    "Папка проекта",
    value=str(ROOT / "projects" / "example"),
)

tab_setup, tab_run, tab_preview = st.tabs(["Настройка", "Запуск", "Превью транскрипта"])

# ── constants & helpers ───────────────────────────────────────────────────────

BASE_COLS = ["transcript_file", "id", "respondent_speaker"]
_SPECIAL_COLS = {"interview_date", "segment"}
_SUPPORTED_EXT = {".docx", ".txt"}


def _sanitize_id(stem: str) -> str:
    s = re.sub(r"[^\w]", "_", stem).strip("_")
    return re.sub(r"_+", "_", s) or "R"


def _discover_files(proj_dir: str, subdir: str) -> list[Path]:
    tdir = Path(proj_dir) / subdir
    if not tdir.exists():
        return []
    return sorted(
        p for p in tdir.iterdir()
        if p.suffix.lower() in _SUPPORTED_EXT and not p.name.startswith(".")
    )


def _df_from_respondents(respondents, default_speaker: str, extra_cols: list[str]) -> pd.DataFrame:
    cols = BASE_COLS + extra_cols
    rows = []
    for r in respondents:
        row: dict = {
            "transcript_file": r.transcript_file,
            "id": r.id,
            "respondent_speaker": r.respondent_speaker or default_speaker,
        }
        for col in extra_cols:
            if col == "segment":
                row[col] = r.segment or ""
            elif col == "interview_date":
                row[col] = r.interview_date or ""
            else:
                row[col] = r.extra.get(col, "")
        rows.append(row)
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def _df_from_files(files: list[Path], extra_cols: list[str]) -> pd.DataFrame:
    cols = BASE_COLS + extra_cols
    rows = [
        {
            "transcript_file": f.name,
            "id": _sanitize_id(f.stem),
            "respondent_speaker": "",
            **{c: "" for c in extra_cols},
        }
        for f in files
    ]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


# ── reset session state when project changes ─────────────────────────────────

if st.session_state.get("_proj") != project_dir:
    st.session_state._proj = project_dir
    for k in ("resp_df", "extra_cols"):
        st.session_state.pop(k, None)

# ── TAB: Настройка ────────────────────────────────────────────────────────────

with tab_setup:
    st.subheader("Проект")

    try:
        config = load_config(project_dir)
        loaded = True
    except FileNotFoundError:
        config = None
        loaded = False
        st.info("Создайте project.yaml через форму ниже или скопируйте projects/example")

    research_topic = st.text_area(
        "Тема исследования *",
        value=config.research_topic if loaded else "",
        height=80,
    )
    research_goals = st.text_area(
        "Цели исследования",
        value=config.research_goals if loaded else "",
    )
    hypotheses = st.text_area(
        "Гипотезы (по одной на строку)",
        value="\n".join(config.hypotheses) if loaded else "",
    )
    questions = st.text_area(
        "Вопросы исследования (по одному на строку)",
        value="\n".join(config.research_questions) if loaded else "",
    )

    # ── Related themes: LLM merges into a single editable textarea ────────────
    related_key = f"related_{project_dir}"
    if related_key not in st.session_state:
        st.session_state[related_key] = "\n".join(config.related_themes) if loaded else ""

    if st.button("Сгенерировать связанные темы (LLM)"):
        from coder.config import ProjectConfig

        tmp = ProjectConfig(
            research_topic=research_topic,
            hypotheses=[h.strip() for h in hypotheses.splitlines() if h.strip()],
            research_questions=[q.strip() for q in questions.splitlines() if q.strip()],
        )
        new_themes = suggest_related_themes(tmp)
        existing = {t.strip() for t in st.session_state[related_key].splitlines() if t.strip()}
        merged = list(existing) + [t for t in new_themes if t not in existing]
        st.session_state[related_key] = "\n".join(merged)
        st.rerun()

    st.text_area("Связанные темы (по одной на строку)", key=related_key)

    # global speaker: preserved from config for CLI fallback, not shown in UI
    _global_speaker = config.respondent_speaker if loaded else "Speaker 2"

    # ── Run settings ──────────────────────────────────────────────────────────
    col_mode, col_skip = st.columns(2)
    with col_mode:
        run_mode = st.selectbox(
            "Режим прогона",
            ["test", "full"],
            index=0 if (not loaded or config.run_mode == RunMode.TEST) else 1,
        )
    with col_skip:
        skip_filter = st.checkbox(
            "Пропустить LLM-фильтрацию",
            value=config.skip_filter if loaded else False,
        )

    if run_mode == "test":
        col_st, col_sv = st.columns(2)
        with col_st:
            scope_type = st.selectbox(
                "Тестовый срез",
                ["on_topic_utterances", "duration_minutes"],
                index=0 if (
                    not loaded or config.test_scope.type == TestScopeType.ON_TOPIC_UTTERANCES
                ) else 1,
            )
        with col_sv:
            scope_value = st.number_input(
                "Значение среза",
                min_value=1,
                value=config.test_scope.value if loaded else 20,
            )
    else:
        scope_type = "on_topic_utterances"
        scope_value = 20

    # ── Respondents table ─────────────────────────────────────────────────────
    st.subheader("Респонденты")
    st.caption(
        "**Файл транскрипта**, **ID** и **Спикер** — базовые столбцы. "
        "Добавляй любые дополнительные столбцы и называй их как хочешь."
    )

    transcripts_subdir = config.transcripts_dir if loaded else "transcripts"

    # Initialize extra_cols from saved respondent_fields
    if "extra_cols" not in st.session_state:
        if loaded and config.respondent_fields:
            st.session_state.extra_cols = [
                f.key for f in config.respondent_fields if f.key not in set(BASE_COLS)
            ]
        else:
            st.session_state.extra_cols = []

    # Initialize resp_df from saved respondents or auto-discover
    if "resp_df" not in st.session_state:
        if loaded and config.respondents:
            st.session_state.resp_df = _df_from_respondents(
                config.respondents, "", st.session_state.extra_cols
            )
        else:
            files = _discover_files(project_dir, transcripts_subdir)
            st.session_state.resp_df = _df_from_files(files, st.session_state.extra_cols)

    # ── Controls: discover | add column ──────────────────────────────────────
    c1, c2, c3 = st.columns([2, 4, 1])
    with c1:
        if st.button("Обнаружить транскрипты"):
            files = _discover_files(project_dir, transcripts_subdir)
            # Preserve existing edits: only add rows for newly found files
            existing_files = set(st.session_state.resp_df["transcript_file"].astype(str))
            new_rows = _df_from_files(
                [f for f in files if f.name not in existing_files],
                st.session_state.extra_cols,
            )
            if not new_rows.empty:
                st.session_state.resp_df = pd.concat(
                    [st.session_state.resp_df, new_rows], ignore_index=True
                )
            st.rerun()
    with c2:
        new_col = st.text_input(
            "_col",
            label_visibility="collapsed",
            placeholder="Название нового столбца…",
            key="new_col_input",
        )
    with c3:
        if st.button("+ Столбец"):
            nc = new_col.strip()
            if nc and nc not in BASE_COLS and nc not in st.session_state.extra_cols:
                st.session_state.extra_cols.append(nc)
                st.session_state.resp_df[nc] = ""
                st.rerun()

    # ── Data editor ───────────────────────────────────────────────────────────
    st.caption("Столбцы со ★ обязательны для кодировки.")
    edited_df: pd.DataFrame = st.data_editor(
        st.session_state.resp_df,
        column_config={
            "transcript_file": st.column_config.TextColumn("Файл транскрипта ★", width="large"),
            "id": st.column_config.TextColumn("ID ★", width="small"),
            "respondent_speaker": st.column_config.TextColumn("Спикер ★", width="medium"),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
    )
    st.session_state.resp_df = edited_df

    # ── Rename / delete column ────────────────────────────────────────────────
    if st.session_state.extra_cols:
        with st.expander("Управление столбцами"):
            rc1, rc2, rc3 = st.columns([3, 3, 1])
            with rc1:
                col_to_rename = st.selectbox(
                    "Столбец", st.session_state.extra_cols, key="rename_src"
                )
            with rc2:
                new_name = st.text_input(
                    "Новое название", key="rename_dst", label_visibility="collapsed",
                    placeholder="Новое название…"
                )
            with rc3:
                if st.button("Переименовать"):
                    nn = new_name.strip()
                    if nn and nn != col_to_rename and nn not in BASE_COLS and nn not in st.session_state.extra_cols:
                        idx = st.session_state.extra_cols.index(col_to_rename)
                        st.session_state.extra_cols[idx] = nn
                        st.session_state.resp_df = st.session_state.resp_df.rename(
                            columns={col_to_rename: nn}
                        )
                        st.rerun()

            dc1, dc2 = st.columns([5, 1])
            with dc1:
                col_to_delete = st.selectbox(
                    "Удалить столбец", st.session_state.extra_cols, key="delete_col_src"
                )
            with dc2:
                if st.button("Удалить", type="secondary", key="delete_col_btn"):
                    st.session_state.extra_cols.remove(col_to_delete)
                    st.session_state.resp_df = st.session_state.resp_df.drop(
                        columns=[col_to_delete], errors="ignore"
                    )
                    st.rerun()

    id_col = edited_df.get("id", pd.Series(dtype=str)).astype(str).str.strip()
    file_col = edited_df.get("transcript_file", pd.Series(dtype=str)).astype(str).str.strip()
    speaker_col = edited_df.get("respondent_speaker", pd.Series(dtype=str)).astype(str).str.strip()
    if edited_df.empty or id_col.replace("nan", "").eq("").all():
        st.info(
            f"Список пуст — при запуске программа автоматически найдёт все .docx/.txt "
            f"в папке `{transcripts_subdir}/`."
        )
    else:
        missing = edited_df[
            id_col.replace("nan", "").eq("") | file_col.replace("nan", "").eq("")
        ]
        if not missing.empty:
            st.warning(f"⚠️ {len(missing)} строк без Файла или ID — они будут пропущены при сохранении.")
        bad_speaker = edited_df[speaker_col.replace("nan", "").eq("")]
        if not bad_speaker.empty:
            st.warning(f"⚠️ {len(bad_speaker)} строк без Спикера — реплики респондента не будут распознаны и наблюдения не появятся.")

    # ── Save ──────────────────────────────────────────────────────────────────
    if st.button("Сохранить project.yaml"):
        from coder.config import ProjectConfig

        extra_col_names = [c for c in edited_df.columns if c not in set(BASE_COLS)]
        respondents_list: list[RespondentMeta] = []

        for _, row in edited_df.iterrows():
            rid = str(row.get("id", "")).strip()
            rfile = str(row.get("transcript_file", "")).strip()
            if not rid or rid == "nan" or not rfile or rfile == "nan":
                continue
            rspeaker = str(row.get("respondent_speaker", "")).strip()

            extra: dict = {}
            for col in extra_col_names:
                if col in _SPECIAL_COLS:
                    continue
                val = str(row.get(col, "")).strip()
                if val and val != "nan":
                    extra[col] = val

            def _cell(col: str) -> str | None:
                if col not in extra_col_names:
                    return None
                v = str(row.get(col, "")).strip()
                return v if v and v != "nan" else None

            respondents_list.append(RespondentMeta(
                id=rid,
                transcript_file=rfile,
                respondent_speaker=rspeaker or None,
                interview_date=_cell("interview_date"),
                segment=_cell("segment"),
                extra=extra,
            ))

        respondent_fields_list = [
            RespondentField(
                key=col,
                label=col,
                field_type="date" if col == "interview_date" else "text",
            )
            for col in extra_col_names
        ]

        related_text = st.session_state.get(related_key, "")
        cfg = ProjectConfig(
            name=Path(project_dir).name,
            research_topic=research_topic,
            research_goals=research_goals,
            hypotheses=[h.strip() for h in hypotheses.splitlines() if h.strip()],
            research_questions=[q.strip() for q in questions.splitlines() if q.strip()],
            related_themes=[t.strip() for t in related_text.splitlines() if t.strip()],
            respondent_speaker=_global_speaker,
            run_mode=RunMode(run_mode),
            test_scope=TestScope(type=TestScopeType(scope_type), value=int(scope_value)),
            respondents=respondents_list,
            respondent_fields=respondent_fields_list,
            skip_filter=skip_filter,
        )
        path = save_config(project_dir, cfg)
        st.success(f"Сохранено: {path}")

# ── TAB: Запуск ───────────────────────────────────────────────────────────────

with tab_run:
    st.write("Требуется `DEEPSEEK_API_KEY` (или `OPENAI_API_KEY`) в `.env` в корне репозитория.")
    st.caption("Модель: deepseek-chat, base: https://api.deepseek.com — см. project.yaml → llm_model")

    try:
        _run_cfg = load_config(project_dir)
        _n = len(_run_cfg.respondents)
        if _run_cfg.run_mode.value == "test":
            if _n > 1:
                st.warning(
                    f"⚠️ **Тест-режим:** будет обработан только **первый транскрипт** из {_n}. "
                    "Для кодировки всех переключи режим на **full** на вкладке Настройка."
                )
            else:
                st.info("Тест-режим: первые 20 реплик одного транскрипта.")
        else:
            st.info(f"Full-режим: будут обработаны все {_n} транскрипт(а/ов)." if _n else "Full-режим: авто-обнаружение транскриптов.")
    except Exception:
        pass

    if st.button("Запустить кодирование", type="primary"):
        with st.spinner("Пайплайн…"):
            try:
                result = run_pipeline(project_dir)
                st.success(f"Наблюдений: {result['observations_count']}")
                xlsx_path = Path(result["xlsx"])
                st.write(f"Excel: `{xlsx_path}`")
                st.download_button(
                    "Скачать XLSX",
                    data=xlsx_path.read_bytes(),
                    file_name=xlsx_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception as e:
                st.error(str(e))

# ── TAB: Превью транскрипта ───────────────────────────────────────────────────

with tab_preview:
    st.write("Парсинг без LLM — проверка формата транскрипта.")
    try:
        cfg = load_config(project_dir)
        tpath = project_path(project_dir) / cfg.transcripts_dir
        if cfg.respondents:
            r0 = cfg.respondents[0]
            f = tpath / r0.transcript_file
            if f.exists():
                speaker = r0.respondent_speaker or cfg.respondent_speaker
                tr = parse_transcript_file(f, r0.id, speaker)
                st.metric("Реплик", len(tr.utterances))
                st.metric("Реплик респондента", sum(1 for u in tr.utterances if u.is_respondent))
                for u in tr.utterances[:25]:
                    mark = "🟢" if u.is_respondent else "⚪"
                    st.caption(f"{mark} {u.timestamp_raw} {u.speaker}: {u.text[:200]}")
            else:
                st.warning(f"Положите файл в {tpath}")
        else:
            files = sorted(tpath.glob("*.docx")) + sorted(tpath.glob("*.txt"))
            if files:
                tr = parse_transcript_file(files[0], files[0].stem, cfg.respondent_speaker)
                st.caption(f"Авто-обнаружение: превью `{files[0].name}`")
                st.metric("Реплик", len(tr.utterances))
                st.metric("Реплик респондента", sum(1 for u in tr.utterances if u.is_respondent))
                for u in tr.utterances[:25]:
                    mark = "🟢" if u.is_respondent else "⚪"
                    st.caption(f"{mark} {u.timestamp_raw} {u.speaker}: {u.text[:200]}")
            else:
                st.warning(f"Положите .docx файлы в {tpath}")
    except Exception as e:
        st.error(str(e))
