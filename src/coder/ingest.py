"""Чтение документов (.docx, .md, .txt)."""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAX_DOCX_XML_BYTES = 50 * 1024 * 1024  # 50 МБ распакованного document.xml


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo("word/document.xml")
        if info.file_size > _MAX_DOCX_XML_BYTES:
            raise ValueError(
                f"Файл слишком большой: document.xml занимает "
                f"{info.file_size // 1_048_576} МБ (лимит 50 МБ)"
            )
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    lines: list[str] = []
    for para in root.iter(f"{W_NS}p"):
        parts = [node.text for node in para.iter(f"{W_NS}t") if node.text]
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def load_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return read_docx(path)
    if suffix in {".md", ".txt"}:
        return read_text_file(path)
    raise ValueError(f"Неподдерживаемый формат: {path}")
