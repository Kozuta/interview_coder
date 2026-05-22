"""Расчёт критичности по кластерам (гайд §5)."""

from __future__ import annotations

from collections import Counter, defaultdict

from coder.models import Observation

NEGATIVE_MODALITIES = {"Невозможность", "Необходимость", "Оценка−"}
BARRIER = "Барьер"
PROBLEM = "Проблема"
IGNORANCE = "Незнание возможности"
DISTRUST = "Недоверие / сомнение"


def _has_negative_modality(obs: Observation) -> bool:
    return bool(NEGATIVE_MODALITIES.intersection(obs.modality_tags))


def _pct(n: int, total: int) -> float:
    return (n / total * 100) if total else 0.0


def assign_criticality(observations: list[Observation]) -> dict[str, str]:
    """Returns {cluster_name: 'High'|'Medium'|'Low'} without modifying observations."""
    by_cluster: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        key = obs.affinity_cluster or "Без кластера"
        by_cluster[key].append(obs)

    result: dict[str, str] = {}
    for cluster, items in by_cluster.items():
        total = len(items)
        code_counts: dict[str, int] = defaultdict(int)
        for o in items:
            code_counts[o.primary_code] += 1

        barrier_share = _pct(code_counts.get(BARRIER, 0), total)
        problem_share = _pct(code_counts.get(PROBLEM, 0), total)
        ignorance_share = _pct(code_counts.get(IGNORANCE, 0), total)
        distrust_share = _pct(code_counts.get(DISTRUST, 0), total)

        level = "Low"
        for o in items:
            if o.primary_code == BARRIER and _has_negative_modality(o):
                level = "High"
                break

        if level != "High":
            if barrier_share >= 20:
                level = "High"
            elif any(o.is_key_task and o.primary_code in {PROBLEM, BARRIER} and problem_share >= 30 for o in items):
                level = "High"
            elif any(o.is_key_task and o.primary_code == PROBLEM and 15 <= problem_share < 30 for o in items):
                level = "Medium"
            elif any(o.is_key_task and ignorance_share >= 20 for o in items):
                level = "Medium"
            elif distrust_share >= 20:
                level = "Medium"

        result[cluster] = level

    return result


def build_summary(observations: list[Observation], cluster_crit: dict[str, str]) -> list:
    from coder.models import SummaryRow

    by_cluster: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_cluster[obs.affinity_cluster or obs.normalized_category].append(obs)

    rows: list[SummaryRow] = []
    for cluster, items in sorted(by_cluster.items()):
        total = len(items)
        code_counts = Counter(o.primary_code for o in items)
        dominant_code, dominant_count = code_counts.most_common(1)[0] if code_counts else ("", 0)
        freq_str = f"{dominant_count}/{total}"

        respondent_ids = {o.respondent_id for o in items}
        segments = ", ".join(sorted({
            str(o.respondent_meta.get("segment", ""))
            for o in items
            if o.respondent_meta.get("segment")
        }))
        secondary_codes = ", ".join(sorted({o.secondary_code for o in items if o.secondary_code}))

        rows.append(
            SummaryRow(
                affinity_cluster=cluster,
                normalized_category=items[0].normalized_category or cluster,
                description=items[0].atom,
                observation_ids=[o.id for o in items],
                criticality=cluster_crit.get(cluster, "Low"),
                cluster_frequency=freq_str,
                respondent_count=len(respondent_ids),
                segments=segments,
                secondary_codes=secondary_codes,
                key_params="",
                primary_code=dominant_code,
                count=total,
            )
        )
    return rows
