"""Streamlit UI кодировщика интервью."""

from __future__ import annotations

import sys
from pathlib import Path

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
    related = st.text_area(
        "Связанные темы (по одной на строку)",
        value="\n".join(config.related_themes) if loaded else "",
    )

    if st.button("Предложить связанные темы (LLM)"):
        from coder.config import ProjectConfig

        tmp = ProjectConfig(
            research_topic=research_topic,
            hypotheses=[h.strip() for h in hypotheses.splitlines() if h.strip()],
            research_questions=[q.strip() for q in questions.splitlines() if q.strip()],
        )
        save_config(project_dir, tmp)
        themes = suggest_related_themes(tmp)
        st.session_state["suggested_themes"] = "\n".join(themes)

    if st.session_state.get("suggested_themes"):
        related = st.text_area(
            "Связанные темы (предложены LLM)",
            value=st.session_state["suggested_themes"],
            key="related_suggested",
        )

    respondent_speaker = st.text_input(
        "Респондент (Speaker)",
        value=config.respondent_speaker if loaded else "Speaker 2",
    )
    run_mode = st.selectbox(
        "Режим прогона",
        ["test", "full"],
        index=0 if (not loaded or config.run_mode == RunMode.TEST) else 1,
    )
    scope_type = st.selectbox(
        "Тестовый срез",
        ["on_topic_utterances", "duration_minutes"],
    )
    scope_value = st.number_input("Значение среза", min_value=1, value=20)

    st.subheader("Респондент")
    r_id = st.text_input("ID респондента", value="R01")
    r_file = st.text_input("Файл транскрипта", value="transcript 1.docx")
    r_segment = st.text_input("Сегмент", value=config.respondents[0].segment if loaded and config.respondents else "")
    r_date = st.text_input("Дата интервью", value="2025-01-15")

    if st.button("Сохранить project.yaml"):
        from coder.config import ProjectConfig

        # Сохраняем respondent_fields и полный список респондентов из загруженного конфига —
        # пользователь редактирует их вручную в project.yaml.
        existing_fields = config.respondent_fields if loaded else [RespondentField(key="segment", label="Сегмент")]
        existing_respondents = config.respondents if loaded else []

        # Обновляем только первого респондента из UI, остальных оставляем как есть
        updated_respondents = list(existing_respondents)
        first = RespondentMeta(
            id=r_id,
            transcript_file=r_file,
            segment=r_segment or None,
            interview_date=r_date or None,
            extra=(existing_respondents[0].extra if existing_respondents else {}),
        )
        if updated_respondents:
            updated_respondents[0] = first
        else:
            updated_respondents = [first]

        cfg = ProjectConfig(
            name=Path(project_dir).name,
            research_topic=research_topic,
            research_goals=research_goals,
            hypotheses=[h.strip() for h in hypotheses.splitlines() if h.strip()],
            research_questions=[q.strip() for q in questions.splitlines() if q.strip()],
            related_themes=[t.strip() for t in related.splitlines() if t.strip()],
            respondent_speaker=respondent_speaker,
            run_mode=RunMode(run_mode),
            test_scope=TestScope(
                type=TestScopeType(scope_type),
                value=int(scope_value),
            ),
            respondents=updated_respondents,
            respondent_fields=existing_fields,
            skip_filter=config.skip_filter if loaded else False,
        )
        path = save_config(project_dir, cfg)
        st.success(f"Сохранено: {path}")

with tab_run:
    st.write("Требуется `DEEPSEEK_API_KEY` (или `OPENAI_API_KEY`) в `.env` в корне репозитория.")
    st.caption("Модель: deepseek-chat, base: https://api.deepseek.com — см. project.yaml → llm_model")
    if st.button("Запустить кодирование", type="primary"):
        with st.spinner("Пайплайн…"):
            try:
                result = run_pipeline(project_dir)
                st.success(f"Наблюдений: {result['observations_count']}")
                st.write(f"Excel: `{result['xlsx']}`")
                out = artifacts_dir(project_dir)
                xlsx_files = list(out.glob("*.xlsx"))
                if xlsx_files:
                    st.download_button(
                        "Скачать XLSX",
                        data=xlsx_files[-1].read_bytes(),
                        file_name=xlsx_files[-1].name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            except Exception as e:
                st.error(str(e))

with tab_preview:
    st.write("Парсинг без LLM — проверка формата транскрипта.")
    try:
        cfg = load_config(project_dir)
        tpath = project_path(project_dir) / cfg.transcripts_dir
        if cfg.respondents:
            f = tpath / cfg.respondents[0].transcript_file
            if f.exists():
                tr = parse_transcript_file(f, cfg.respondents[0].id, cfg.respondent_speaker)
                st.metric("Реплик", len(tr.utterances))
                st.metric("Реплик респондента", sum(1 for u in tr.utterances if u.is_respondent))
                for u in tr.utterances[:25]:
                    mark = "🟢" if u.is_respondent else "⚪"
                    st.caption(f"{mark} {u.timestamp_raw} {u.speaker}: {u.text[:200]}")
            else:
                st.warning(f"Положите файл в {tpath}")
    except Exception as e:
        st.error(str(e))
