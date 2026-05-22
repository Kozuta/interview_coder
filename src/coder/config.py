"""Конфигурация проекта исследования."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import AliasChoices, BaseModel, Field

from coder.models import RespondentField, RespondentMeta, RunMode, TestScope


class ProjectConfig(BaseModel):
    name: str = "Исследование"
    research_topic: str
    research_goals: str = ""
    hypotheses: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    related_themes: list[str] = Field(default_factory=list)
    business_context: str = ""
    respondent_speaker: str = "Speaker 2"
    key_product_tasks: list[str] = Field(default_factory=list)
    respondent_fields: list[RespondentField] = Field(default_factory=list)
    respondents: list[RespondentMeta] = Field(default_factory=list)
    run_mode: RunMode = RunMode.TEST
    test_scope: TestScope = Field(default_factory=TestScope)
    skip_filter: bool = False
    llm_model: str = Field(
        default="deepseek-chat",
        validation_alias=AliasChoices("llm_model", "openai_model"),
    )
    transcripts_dir: str = "transcripts"


def project_path(path: str | Path) -> Path:
    return Path(path).resolve()


def load_config(project_dir: str | Path) -> ProjectConfig:
    path = project_path(project_dir) / "project.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Не найден {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ProjectConfig.model_validate(data)


def save_config(project_dir: str | Path, config: ProjectConfig) -> Path:
    root = project_path(project_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "project.yaml"
    payload = config.model_dump(mode="json")
    path.write_text(
        yaml.dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def artifacts_dir(project_dir: str | Path) -> Path:
    d = project_path(project_dir) / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def output_xlsx_path(project_dir: str | Path, config: ProjectConfig) -> Path:
    suffix = "_test" if config.run_mode == RunMode.TEST else ""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in config.name)[:40]
    return artifacts_dir(project_dir) / f"{safe}{suffix}.xlsx"
