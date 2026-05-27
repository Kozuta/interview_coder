# UX Research Database Structure

# Общая архитектура

Система должна быть устроена как multi-layer research database.

Не одна таблица,
а несколько связанных вкладок.

Минимальная структура:

1. Legend / Codebook
2. Raw Coding
3. Cluster Synthesis
4. Insights & Recommendations
5. Research Summary Dashboard

Дополнительно:

6. Respondents
7. JTBD Map
8. Segment Comparison
9. Quote Library

---

# 1. LEGEND / CODEBOOK

Главная reference-вкладка.

Назначение:

- source of truth;
- vocabulary control;
- снижение вариативности кодировки;
- повышение inter-coder reliability;
- повышение AI consistency.

---

## Behavioral codes

| code | definition | when_to_use | when_not_to_use | example |
|---|---|---|---|---|

Пример:

| code | definition |
|---|---|
| Проблема | Пользователь испытывает затруднение, но завершает задачу |
| Барьер | Пользователь отказывается или не завершает задачу |

---

## Modalities

| modality | meaning | linguistic_markers | example |
|---|---|---|---|

Пример:

| modality | linguistic_markers |
|---|---|
| Необходимость | приходится, вынужден |
| Невозможность | не получается, невозможно |

---

## Domain dictionary

| domain | definition |
|---|---|
| Маркетинг | Привлечение клиентов |
| Операционные процессы | Организация работы |

---

## Theme dictionary

| theme | domain | definition |
|---|---|---|

---

## Cluster dictionary

| cluster | theme | definition | example_observations |
|---|---|---|---|

Пример:

| cluster | definition |
|---|---|
| Опора на сарафанное радио | Основной источник клиентов — рекомендации |
| Повторная настройка фильтров | Пользователь заново настраивает фильтры |

---

## Severity rules

| condition | severity |
|---|---|
| Barrier + Невозможность | High |
| Problem + core JTBD + 30% | High |

---

# 2. RAW CODING

Основной production dataset.

Главное правило:

одна строка = один атом.

---

## Рекомендуемая структура

| Поле | Назначение |
|---|---|
| observation_id | Уникальный ID |
| respondent_id | ID респондента |
| segment | Сегмент |
| interview_id | ID интервью |
| timestamp | Таймкод |
| raw_quote | Прямая цитата |
| atomic_observation | Короткий атом |
| primary_code | Основной behavioral code |
| secondary_code | Вторичный код |
| modality | Модальность |
| domain | Продуктовая область |
| theme | Верхнеуровневая тема |
| cluster | Behavioral cluster |
| jtbd | JTBD / задача |
| core_task | Yes / No |
| workaround | Есть ли workaround |
| severity_signal | Barrier / Impossible / Friction |
| analyst_note | Optional |

---

## Важные правила

### raw_quote

Никогда не удалять.

Это evidence layer.

### atomic_observation

Главное поле.

Должно быть:

- коротким;
- machine-readable;
- без интерпретаций.

### cluster

Главное synthesis-поле.

По нему строятся:

- affinity mapping;
- frequency analysis;
- insights;
- recommendations.

---

## Чего не должно быть

Не должно быть полей:

- «Следствие»;
- «Содержание»;
- длинных narrative-комментариев;
- смешения observation и insight.

---

# 3. CLUSTER SYNTHESIS

Промежуточный synthesis layer между raw coding и report.

---

## Структура

| cluster | theme | domain | evidence_count | respondent_count | segments | dominant_codes | dominant_modalities | severity | representative_quotes | synthesis_note |
|---|---|---|---|---|---|---|---|---|---|---|

---

## Ключевые поля

### evidence_count

Количество атомов.

### respondent_count

Количество уникальных респондентов.

### dominant_codes

Доминирующие behavioral codes.

### dominant_modalities

Доминирующие модальности.

### representative_quotes

1–3 лучшие evidence quotes.

### synthesis_note

Короткое описание recurring phenomenon.

Без рекомендаций.

---

# 4. INSIGHTS & RECOMMENDATIONS

Только здесь появляются:

- инсайты;
- продуктовые выводы;
- рекомендации.

---

## Структура

| insight_id | insight | supporting_clusters | affected_segments | severity | business_impact | ux_impact | recommendation | confidence |
|---|---|---|---|---|---|---|---|---|

---

# 5. RESEARCH SUMMARY DASHBOARD

Stakeholder layer.

Минимум текста.
Максимум signal strength.

---

## Что должно быть

### Top High Severity Clusters

| cluster | severity | respondents | affected_jtbd |
|---|---|---|---|

### Top Drivers

| cluster | value |
|---|---|

### Segment Differences

| segment | unique_patterns |
|---|---|

### Core Barriers

| barrier | impact |
|---|---|

### Opportunity Areas

| opportunity | supporting_evidence |
|---|---|

---

# Дополнительные вкладки

## RESPONDENTS

| respondent_id | segment | business_type | experience | geography | notes |
|---|---|---|---|---|---|

---

## JTBD MAP

| jtbd | related_clusters | barriers | drivers | unmet_needs |
|---|---|---|---|---|

---

## SEGMENT COMPARISON

| cluster | segment_A | segment_B | difference |
|---|---|---|---|

---

## QUOTE LIBRARY

| quote | cluster | insight | emotional_strength |
|---|---|---|---|

---

# Идеальный research pipeline

## Layer 1

Interview transcript

↓

## Layer 2

Atomic observations

↓

## Layer 3

Behavioral coding

↓

## Layer 4

Affinity clusters

↓

## Layer 5

Cross-interview synthesis

↓

## Layer 6

Insights

↓

## Layer 7

Recommendations

---

# Главная идея

Dataset должен работать как research operating system.

Тогда:

- AI сможет стабильно кластеризовать данные;
- synthesis станет качественнее;
- отчёты будут собираться быстрее;
- появится traceability:

insight → cluster → quote → respondent
