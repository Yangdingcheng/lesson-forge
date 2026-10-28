"""目标对齐校验（确定性审计）：把「课标对齐」从口号变成可检查的矩阵。

检查项：
- 孤儿目标：没有任何教学环节承载的目标
- 无评价目标：没有习题也没有量规条目的目标
- 野习题：习题引用的目标 ID 不存在
- 裸环节：环节没有绑定任何目标
- 课标缺口：工程列出的课标条目没有任何目标引用
- 量规缺口：有目标却没有评价量规行
- 时间核账：环节分钟数之和与课时总长偏差 > 5 分钟
输出对齐矩阵（目标 × 环节/习题/量规）与覆盖率分数。
"""

from __future__ import annotations

from .models import Project


def check_alignment(p: Project) -> dict:
    obj_ids = [o.id for o in p.objectives]
    obj_set = set(obj_ids)
    sections_by_obj: dict[str, list[str]] = {oid: [] for oid in obj_ids}
    bare_sections: list[str] = []
    for s in p.sections:
        if not s.objective_ids:
            bare_sections.append(s.id)
        for oid in s.objective_ids:
            if oid in sections_by_obj:
                sections_by_obj[oid].append(s.id)
    exercises_by_obj: dict[str, list[str]] = {oid: [] for oid in obj_ids}
    wild_exercises: list[str] = []
    for e in p.exercises:
        if e.objective_id in exercises_by_obj:
            exercises_by_obj[e.objective_id].append(e.id)
        else:
            wild_exercises.append(e.id)
    rubric_objs = {r.objective_id for r in p.rubric}

    orphan_objectives = [oid for oid in obj_ids if not sections_by_obj[oid]]
    unassessed = [oid for oid in obj_ids
                  if not exercises_by_obj[oid] and oid not in rubric_objs]
    rubric_missing = [oid for oid in obj_ids if oid not in rubric_objs]

    covered_standards = {o.standard_ref.strip() for o in p.objectives if o.standard_ref.strip()}
    uncovered_standards = [s for s in p.standards
                           if s.strip() and s.strip() not in covered_standards
                           and not any(s.strip() in c or c in s.strip() for c in covered_standards)]

    total_minutes = sum(s.minutes for s in p.sections)
    time_ok = abs(total_minutes - p.period_minutes) <= 5

    matrix = []
    fully = 0
    for oid in obj_ids:
        row = {"objective_id": oid,
               "sections": sections_by_obj[oid],
               "exercises": exercises_by_obj[oid],
               "rubric": oid in rubric_objs}
        row["covered"] = bool(row["sections"]) and (bool(row["exercises"]) or row["rubric"])
        fully += 1 if row["covered"] else 0
        matrix.append(row)
    coverage = round(100 * fully / len(obj_ids)) if obj_ids else 0

    issues: list[str] = []
    if not obj_ids:
        issues.append("还没有学习目标。")
    for oid in orphan_objectives:
        issues.append(f"目标 {oid} 没有任何教学环节承载（孤儿目标）。")
    for oid in unassessed:
        issues.append(f"目标 {oid} 没有习题也没有评价量规（无评价目标）。")
    for eid in wild_exercises:
        issues.append(f"习题 {eid} 引用的目标不存在（野习题）。")
    for sid in bare_sections:
        issues.append(f"环节 {sid} 没有绑定任何学习目标（裸环节）。")
    for s in uncovered_standards:
        issues.append(f"课标条目未被任何目标覆盖：{s[:40]}")
    for oid in rubric_missing:
        issues.append(f"目标 {oid} 缺少评价量规。")
    if p.sections and not time_ok:
        issues.append(f"环节总时长 {total_minutes} 分钟，与课时 {p.period_minutes} 分钟偏差超过 5 分钟。")

    return {
        "matrix": matrix,
        "coverage_pct": coverage,
        "orphan_objectives": orphan_objectives,
        "unassessed_objectives": unassessed,
        "wild_exercises": wild_exercises,
        "bare_sections": bare_sections,
        "uncovered_standards": uncovered_standards,
        "rubric_missing": rubric_missing,
        "total_minutes": total_minutes,
        "time_ok": time_ok,
        "issues": issues,
        "ok": not issues,
    }
