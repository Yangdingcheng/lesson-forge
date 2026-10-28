"""五步生成器：目标 → 大纲 → 细化 → 材料（习题/量规/板书）。

每一步都先查知识库接地，再走 AI（结构化 JSON）；没有 Key 或 AI 失败时落到模板模式，
模板产物结构完整、对齐可过，内容留「（请教师修改）」标记——结构靠程序，质量靠教师。
"""

from __future__ import annotations

from .ai_client import AIClient, extract_json
from .alignment import check_alignment
from .kb import KnowledgeBase
from .models import Exercise, Objective, Project, RubricRow, Section

SYSTEM = ("你是一位资深教研员，正在协助一线教师分步备课。要求：严格依据给定的课标条目与知识库材料，"
          "不超纲、不编造教材页码；语言是规范的教案语言；只输出 JSON，不要任何解释文字。")

DIMENSIONS = ["核心素养", "知识与技能", "过程与方法", "情感态度"]


def build_carryover(prev: Project | None) -> str:
    """回流：上一课的反思 + 未覆盖缺口，作为下一课生成的上下文。"""
    if prev is None:
        return ""
    parts = []
    for r in prev.reflections[-3:]:
        parts.append(f"上节课反思：{r.get('text', '')}")
    rep = check_alignment(prev)
    for issue in rep["issues"][:4]:
        parts.append(f"上节课对齐缺口：{issue}")
    return "\n".join(parts)


class Workflow:
    def __init__(self, ai: AIClient | None = None, kb: KnowledgeBase | None = None):
        self.ai = ai
        self.kb = kb

    def _kb_ctx(self, query: str) -> str:
        return self.kb.context_block(query, k=5) if self.kb else ""

    def _meta(self, p: Project) -> str:
        return (f"学科：{p.subject}｜年级：{p.grade}｜教材：{p.textbook}｜单元：{p.unit}｜"
                f"课题：{p.title}｜课时：{p.period_minutes} 分钟\n"
                f"本课课标条目：\n" + "\n".join(f"- {s}" for s in p.standards))

    # ---------- 步骤 1：学习目标 ----------
    def gen_objectives(self, p: Project, carryover: str = "") -> list[Objective]:
        ctx = self._kb_ctx(f"{p.subject} {p.title} 课程标准 学习目标")
        if self.ai and self.ai.available():
            user = (f"{self._meta(p)}\n{ctx}\n{carryover}\n"
                    "任务：设计 3–4 条学习目标。每条目标给出 dimension（核心素养维度）与 standard_ref（从上面课标条目中原文引用一条）。\n"
                    '输出 JSON：{"objectives":[{"text":"...","dimension":"...","standard_ref":"..."}]}')
            data = extract_json(self.ai.chat(SYSTEM, user))
            if data and data.get("objectives"):
                out = []
                for i, o in enumerate(data["objectives"][:5], 1):
                    out.append(Objective(id=f"G{i}", text=str(o.get("text", "")).strip(),
                                         dimension=str(o.get("dimension", "知识与技能")),
                                         standard_ref=str(o.get("standard_ref", "")).strip()))
                return [o for o in out if o.text]
        # 模板回退：一条课标 → 一条目标
        out = []
        standards = p.standards or [f"围绕「{p.title}」的核心内容"]
        for i, s in enumerate(standards[:4], 1):
            out.append(Objective(
                id=f"G{i}",
                text=f"理解并掌握与「{s[:28]}」相关的内容，能用自己的话解释并完成基础应用。（请教师修改）",
                dimension=DIMENSIONS[(i - 1) % len(DIMENSIONS)],
                standard_ref=s))
        return out

    # ---------- 步骤 2：流程大纲 ----------
    def gen_outline(self, p: Project) -> list[Section]:
        obj_ids = [o.id for o in p.objectives]
        ctx = self._kb_ctx(f"{p.title} 教学过程 导入 探究")
        if self.ai and self.ai.available() and obj_ids:
            user = (f"{self._meta(p)}\n{ctx}\n学习目标：\n" +
                    "\n".join(f"- {o.id}：{o.text}" for o in p.objectives) +
                    f"\n任务：设计教学环节（总时长 {p.period_minutes} 分钟），每个环节绑定它承载的目标 ID（只能用上面给出的 ID）。\n"
                    '输出 JSON：{"sections":[{"title":"...","minutes":5,"objective_ids":["G1"]}]}')
            data = extract_json(self.ai.chat(SYSTEM, user))
            if data and data.get("sections"):
                out = []
                for i, s in enumerate(data["sections"][:8], 1):
                    ids = [x for x in s.get("objective_ids", []) if x in obj_ids]
                    out.append(Section(id=f"S{i}", title=str(s.get("title", f"环节{i}")),
                                       minutes=int(s.get("minutes", 5) or 5), objective_ids=ids))
                if out:
                    return out
        # 模板回退：经典五环节，时长按比例，总和 = 课时
        total = p.period_minutes
        plan = [("情境导入", 0.11), ("探究新知", 0.33), ("例题/讲解示范", 0.18),
                ("分层练习", 0.27), ("小结与作业", 0.11)]
        out = []
        assigned = 0
        for i, (title, ratio) in enumerate(plan, 1):
            mins = max(3, round(total * ratio))
            assigned += mins
            ids: list[str] = []
            if obj_ids:
                if title in ("情境导入", "探究新知", "例题/讲解示范", "分层练习"):
                    ids = list(obj_ids)   # 导入环节呈现并引出全部目标
                elif title == "小结与作业":
                    ids = obj_ids[:1]
            out.append(Section(id=f"S{i}", title=title, minutes=mins, objective_ids=ids))
        if out:
            out[1].minutes += total - assigned  # 差值补进探究环节
        return out

    # ---------- 步骤 3：环节细化 ----------
    def gen_details(self, p: Project) -> list[Section]:
        ctx = self._kb_ctx(f"{p.title} 教学活动 设计意图")
        obj_text = {o.id: o.text for o in p.objectives}
        if self.ai and self.ai.available():
            brief = "\n".join(f"- {s.id}《{s.title}》({s.minutes}分钟) 目标:{','.join(s.objective_ids)}"
                              for s in p.sections)
            user = (f"{self._meta(p)}\n{ctx}\n环节大纲：\n{brief}\n"
                    "任务：为每个环节写教师活动、学生活动、设计意图，并给出基础/提高/挑战三层任务。\n"
                    '输出 JSON：{"details":[{"id":"S1","teacher_activity":"...","student_activity":"...",'
                    '"intent":"...","levels":{"基础":"...","提高":"...","挑战":"..."}}]}')
            data = extract_json(self.ai.chat(SYSTEM, user))
            if data and data.get("details"):
                by_id = {str(d.get("id")): d for d in data["details"]}
                for s in p.sections:
                    d = by_id.get(s.id)
                    if d:
                        s.teacher_activity = str(d.get("teacher_activity", ""))
                        s.student_activity = str(d.get("student_activity", ""))
                        s.intent = str(d.get("intent", ""))
                        lv = d.get("levels") or {}
                        s.levels = {k: str(lv.get(k, "")) for k in ("基础", "提高", "挑战")}
                return p.sections
        for s in p.sections:
            targets = "、".join(obj_text.get(i, i) for i in s.objective_ids) or "本课目标"
            s.teacher_activity = f"围绕「{s.title}」组织教学，讲解与提问结合，关注学生对{targets[:30]}的理解。（请教师修改）"
            s.student_activity = f"听讲、思考并参与「{s.title}」的活动与讨论，完成相应任务。（请教师修改）"
            s.intent = f"服务目标：{targets[:60]}"
            s.levels = {
                "基础": f"完成「{s.title}」的基础任务，能复述关键内容。",
                "提高": f"能独立完成「{s.title}」的变式任务并说明思路。",
                "挑战": f"尝试「{s.title}」的拓展问题，尝试用多种方法解决。",
            }
        return p.sections

    # ---------- 步骤 4：材料（习题 + 量规 + 板书） ----------
    def gen_materials(self, p: Project):
        ctx = self._kb_ctx(f"{p.title} 练习题 评价")
        exercises: list[Exercise] = []
        if self.ai and self.ai.available() and p.objectives:
            brief = "\n".join(f"- {o.id}：{o.text}" for o in p.objectives)
            user = (f"{self._meta(p)}\n{ctx}\n学习目标：\n{brief}\n"
                    "任务：为每个目标各设计 3 道题（基础/提高/挑战各一），给出参考答案；再给出一份板书设计文本。\n"
                    '输出 JSON：{"exercises":[{"stem":"...","answer":"...","objective_id":"G1","level":"基础"}],'
                    '"board":"..."}')
            data = extract_json(self.ai.chat(SYSTEM, user))
            if data and data.get("exercises"):
                valid = {o.id for o in p.objectives}
                for i, e in enumerate(data["exercises"][:16], 1):
                    oid = str(e.get("objective_id", ""))
                    if oid not in valid:
                        continue
                    exercises.append(Exercise(
                        id=f"E{i}", stem=str(e.get("stem", "")), answer=str(e.get("answer", "")),
                        objective_id=oid, level=str(e.get("level", "基础")), kind="练习"))
                board = str(data.get("board", ""))
                if exercises:
                    return exercises, self._rubric(p), board
        # 模板回退
        n = 0
        for o in p.objectives:
            for level in ("基础", "提高", "挑战"):
                n += 1
                exercises.append(Exercise(
                    id=f"E{n}",
                    stem=f"（{level}）围绕目标「{o.text[:36]}」命制一道题，题干与数据请教师替换为教材原题或改编题。",
                    answer="（请教师填写参考答案与评分要点）",
                    objective_id=o.id, level=level, kind="练习"))
        board_lines = [p.title, ""]
        for s in p.sections:
            board_lines.append(f"{s.title}（{s.minutes} 分钟）")
        board_lines += ["", "学习目标："] + [f"{o.id} {o.text[:40]}" for o in p.objectives]
        return exercises, self._rubric(p), "\n".join(board_lines)

    @staticmethod
    def _rubric(p: Project) -> list[RubricRow]:
        rows = []
        for o in p.objectives:
            short = o.text[:30]
            rows.append(RubricRow(
                objective_id=o.id,
                excellent=f"能完整达成「{short}」，并能迁移到新情境。",
                good=f"基本达成「{short}」，细节有少量疏漏。",
                developing=f"尚未达成「{short}」，需要教师或同伴支架。"))
        return rows
