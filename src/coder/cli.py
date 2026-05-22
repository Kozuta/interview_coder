"""CLI кодировщика."""

from __future__ import annotations

import argparse
import sys

from coder.config import load_config, save_config
from coder.pipeline import run_pipeline, suggest_related_themes


def main() -> None:
    parser = argparse.ArgumentParser(description="Кодировщик интервью")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Запустить пайплайн")
    run_p.add_argument("--project", required=True, help="Папка проекта с project.yaml")

    themes_p = sub.add_parser("themes", help="Сгенерировать связанные темы")
    themes_p.add_argument("--project", required=True)

    args = parser.parse_args()

    if args.command == "run":
        result = run_pipeline(args.project)
        print(f"Готово: {result['observations_count']} наблюдений")
        print(f"Excel: {result['xlsx']}")
    elif args.command == "themes":
        config = load_config(args.project)
        themes = suggest_related_themes(config)
        config.related_themes = themes
        save_config(args.project, config)
        print("Связанные темы:")
        for t in themes:
            print(f"  - {t}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
