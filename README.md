# Interview Coder

Инструмент автоматической качественной кодировки UX/CX-интервью. Преобразует транскрипты `.docx` в структурированный Excel-файл с атомарными наблюдениями, affinity-кластерами и кодбуком.

## Что делает

Пайплайн из пяти шагов на основе LLM:

1. **Фильтрация** — отделяет реплики по теме от small talk, оргвопросов, эхо-реакций
2. **Атомизация** — дробит реплики на атомарные наблюдения: одна мысль / действие / эмоция
3. **Affinity-группировка** — объединяет наблюдения в тематические кластеры; названия — инсайты, не ярлыки
4. **Кодировка по кодбуку** — присваивает первичный и вторичный коды, модальные теги, флаг ключевой задачи
5. **Экспорт в Excel** — лист «Кодировка» (все наблюдения) + лист «Сводная» (по кластерам) + служебные листы

### Кодбук

| Слой | Коды |
|------|------|
| Сценарий | Задача, Триггер, Паттерн поведения |
| Механизм | Драйвер, Проблема, Барьер |
| Ментальная модель | Ценность, Незнание возможности, Недоверие / сомнение |

Модальные теги: Необходимость, Невозможность, Возможность, Уверенность, Сомнение, Оценка+, Оценка−, Норма, Желательность, Гипотетичность.

### Структура Excel-файла

| Лист | Содержимое |
|------|------------|
| **Кодировка** | Все наблюдения: атом, цитата, содержание, контекст, кластер, код, код 2, модальность |
| **Сводная** | По кластерам: кол-во респондентов, частота, коды, сегменты, критичность, ID наблюдений |
| Транскрипты | Исходные реплики с привязкой к наблюдениям |
| Исключено | Реплики, не вошедшие в кодировку, с причиной |
| Респонденты | Метаданные респондентов |
| Настройки | Параметры проекта |
| Справочник | Коды и модальности |

## Требования

- Python 3.11+
- Windows (скрипты `.ps1`) или любая ОС через прямые команды
- API-ключ DeepSeek или OpenAI

## Установка

```powershell
# Клонировать репозиторий и перейти в папку
git clone https://github.com/your-org/interview-coder.git
cd interview-coder

# Создать venv и установить зависимости
.\setup.ps1

# Создать .env с API-ключом
copy .env.example .env
# Открыть .env и вставить DEEPSEEK_API_KEY или OPENAI_API_KEY
```

## Быстрый старт

```powershell
# Веб-интерфейс (рекомендуется)
.\ui.ps1

# Кодировка из командной строки
.\run.ps1                   # проект по умолчанию: projects/example
.\run.ps1 projects/my-study # свой проект
```

Результат: `projects/<name>/output/<name>_test.xlsx` (в полном режиме — без суффикса `_test`).

## Создание проекта

1. Скопировать папку `projects/example` в `projects/<my-study>`
2. Отредактировать `project.yaml` (см. справочник ниже)
3. Положить транскрипты `.docx` в `projects/<my-study>/transcripts/`
4. Запустить

```powershell
.\run.ps1 projects/my-study
```

## Формат транскрипта

Файл `.docx` со стандартной разметкой Zoom / Teams:

```
0:00  Speaker 1
Здравствуйте, расскажите о себе.

0:15  Speaker 2
Я работаю менеджером по продажам уже пять лет...
```

Метка времени `М:СС` или `ЧЧ:ММ:СС`, затем имя спикера на той же или следующей строке.

## Справочник `project.yaml`

```yaml
name: my-study                    # название проекта (используется в имени xlsx)
research_topic: "Тема"            # обязательно — передаётся в каждый промпт
research_goals: "Цели"
hypotheses:
  - "Гипотеза 1"
research_questions:
  - "Вопрос 1"
related_themes:                   # подтемы для LLM-фильтра (8-15 штук)
  - "Тема 1"
business_context: ""              # дополнительный контекст продукта/бизнеса

respondent_speaker: "Speaker 2"   # имя спикера-респондента в транскрипте

run_mode: test                    # test | full
test_scope:
  type: on_topic_utterances       # on_topic_utterances | duration_minutes
  value: 20

skip_filter: false                # true — пропустить LLM-фильтрацию (быстрее, менее точно)

llm_model: deepseek-chat          # deepseek-chat | gpt-4o | gpt-4o-mini | любая OpenAI-совместимая
transcripts_dir: transcripts      # папка с .docx относительно project.yaml

# Кастомные поля респондента — появятся как отдельные столбцы в листе «Кодировка»
respondent_fields:
  - key: segment
    label: "Сегмент"
    field_type: text              # text | date | select
  - key: city
    label: "Город"
    field_type: text
  - key: platform
    label: "Платформа"
    field_type: text

# Список респондентов
respondents:
  - id: R01
    transcript_file: "interview_anna.docx"
    interview_date: "2025-03-10"
    segment: "Enterprise"
    extra:                        # значения кастомных полей из respondent_fields
      city: "Москва"
      platform: "iOS"
  - id: R02
    transcript_file: "interview_igor.docx"
    interview_date: "2025-03-12"
    segment: "SMB"
    extra:
      city: "Санкт-Петербург"
      platform: "Android"
```

## Переменные окружения (`.env`)

```
# DeepSeek (по умолчанию, дешевле)
DEEPSEEK_API_KEY=sk-...

# OpenAI (если нужен GPT-4o)
OPENAI_API_KEY=sk-...
```

Если указаны оба — приоритет у `DEEPSEEK_API_KEY`.

## CLI

```powershell
# Активировать venv
.\.venv\Scripts\Activate.ps1

# Предложить связанные темы (через LLM)
coder themes --project projects/my-study

# Запустить кодировку
coder run --project projects/my-study

# Запустить кодировку без LLM-фильтра
coder run --project projects/my-study --skip-filter

# Без активации venv
.\.venv\Scripts\python.exe -m coder run --project projects/my-study
```

## Веб-интерфейс

```powershell
.\ui.ps1
# или
.\.venv\Scripts\python.exe -m streamlit run ui/app.py
```

Вкладки:
- **Настройка** — редактировать и сохранить `project.yaml` через форму
- **Запуск** — запустить пайплайн и скачать Excel
- **Превью транскрипта** — проверить парсинг `.docx` без вызова LLM

## Структура репозитория

```
interview-coder/
├── src/coder/
│   ├── pipeline.py       # оркестрация пяти шагов
│   ├── prompts.py        # все LLM-промпты и кодбук
│   ├── models.py         # Pydantic-модели данных
│   ├── transcript.py     # парсинг .docx
│   ├── relevance.py      # шаг 1: LLM-фильтрация
│   ├── criticality.py    # расчёт критичности и сводной
│   ├── export_xlsx.py    # экспорт в Excel
│   ├── config.py         # загрузка/сохранение project.yaml
│   ├── llm.py            # обёртка над OpenAI-клиентом
│   └── cli.py            # точка входа CLI
├── ui/app.py             # Streamlit-интерфейс
├── projects/
│   └── example/          # шаблон проекта (транскрипты не включены)
│       ├── project.yaml
│       └── transcripts/  # положите сюда .docx
├── .claude/commands/
│   └── cluster-naming.md # /cluster-naming — проверка названий кластеров (Claude Code)
├── .env.example
├── pyproject.toml
├── setup.ps1
├── run.ps1
└── ui.ps1
```

## Важно: конфиденциальность данных

Транскрипты интервью содержат персональные данные. В репозиторий они **никогда не попадают** — `.gitignore` исключает все `*.docx`, `*.xlsx` и содержимое папок `transcripts/` и `output/`.

Перед первым `git add` убедитесь:

```powershell
git status   # *.docx и *.xlsx не должны появляться в списке
```

## Лицензия

MIT
