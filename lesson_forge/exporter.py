"""导出标准格式教案（Markdown）：可直接粘贴进 Word 再排版。"""

from __future__ import annotations

from .models import Project


def export_markdown(p: Project) -> str:
    obj = {o.id: o for o in p.objectives}
    lines: list[str] = []
    lines.append(f"# {p.title} · 教案")
    lines.append("")
    lines.append(f"- 学科：{p.subject}｜年级：{p.grade}｜教材：{p.textbook}｜单元：{p.unit}｜课时：{p.period_minutes} 分钟")
    lines.append("")
    if p.standards:
        lines.append("## 一、课程标准")
        for s in p.standards:
            lines.append(f"- {s}")
        lines.append("")
    lines.append("## 二、学习目标")
    lines.append("")
    lines.append("| 编号 | 目标 | 维度 | 对应课标 |")
    lines.append("|---|---|---|---|")
    for o in p.objectives:
        lines.append(f"| {o.id} | {o.text} | {o.dimension} | {o.standard_ref} |")
    lines.append("")
    lines.append("## 三、教学过程")
    lines.append("")
    lines.append("| 环节 | 时间 | 教师活动 | 学生活动 | 设计意图 | 承载目标 |")
    lines.append("|---|---|---|---|---|---|")
    for s in p.sections:
        def cell(t: str) -> str:
            return (t or "").replace("\n", "<br>").replace("|", "｜")
        lines.append(f"| {s.title} | {s.minutes} 分钟 | {cell(s.teacher_activity)} | {cell(s.student_activity)} | {cell(s.intent)} | {', '.join(s.objective_ids)} |")
    lines.append("")
    layered = [s for s in p.sections if s.levels]
    if layered:
        lines.append("### 分层任务")
        for s in layered:
            lines.append(f"- **{s.title}**：基础——{s.levels.get('基础', '')}；提高——{s.levels.get('提高', '')}；挑战——{s.levels.get('挑战', '')}")
        lines.append("")
    if p.exercises:
        lines.append("## 四、习题与检测")
        lines.append("")
        lines.append("| 编号 | 层级 | 题目 | 参考答案 | 对应目标 |")
        lines.append("|---|---|---|---|---|")
        for e in p.exercises:
            lines.append(f"| {e.id} | {e.level} | {e.stem.replace(chr(10), ' ')} | {e.answer.replace(chr(10), ' ')} | {e.objective_id} |")
        lines.append("")
    if p.rubric:
        lines.append("## 五、评价量规")
        lines.append("")
        lines.append("| 目标 | 优秀 | 良好 | 待提高 |")
        lines.append("|---|---|---|---|")
        for r in p.rubric:
            o = obj.get(r.objective_id)
            label = f"{r.objective_id} {o.text[:24] if o else ''}"
            lines.append(f"| {label} | {r.excellent} | {r.good} | {r.developing} |")
        lines.append("")
    if p.board:
        lines.append("## 六、板书设计")
        lines.append("")
        lines.append("```")
        lines.append(p.board)
        lines.append("```")
        lines.append("")
    if p.reflections:
        lines.append("## 七、课后反思")
        for r in p.reflections:
            lines.append(f"- （{r.get('time', '')}）{r.get('text', '')}")
        lines.append("")
    return "\n".join(lines)
