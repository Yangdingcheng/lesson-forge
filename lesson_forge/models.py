"""工程数据模型与 JSON 持久化。

核心设计：学习目标带稳定 ID（G1、G2…），教学环节、习题、评价量规全部引用目标 ID，
这样「目标—活动—评价」一致性可以被程序审计，而不是靠感觉。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field


@dataclass
class Objective:
    id: str
    text: str
    dimension: str = "知识与技能"      # 核心素养维度 / 目标维度
    standard_ref: str = ""            # 对应的课标条目（原文或编号）


@dataclass
class Section:
    id: str
    title: str
    minutes: int = 5
    objective_ids: list[str] = field(default_factory=list)
    teacher_activity: str = ""
    student_activity: str = ""
    intent: str = ""                  # 设计意图
    levels: dict = field(default_factory=dict)   # {"基础": "...", "提高": "...", "挑战": "..."}


@dataclass
class Exercise:
    id: str
    stem: str
    answer: str = ""
    objective_id: str = ""
    level: str = "基础"               # 基础 | 提高 | 挑战
    kind: str = "练习"                # 练习 | 检测 | 作业


@dataclass
class RubricRow:
    objective_id: str
    excellent: str = ""
    good: str = ""
    developing: str = ""


@dataclass
class Project:
    id: str
    title: str                        # 课题
    subject: str = ""
    grade: str = ""
    textbook: str = ""                # 教材版本，如「人教版八年级上册」
    unit: str = ""
    period_minutes: int = 45
    standards: list[str] = field(default_factory=list)   # 本课涉及课标条目
    objectives: list[Objective] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    exercises: list[Exercise] = field(default_factory=list)
    rubric: list[RubricRow] = field(default_factory=list)
    board: str = ""                   # 板书设计
    reflections: list[dict] = field(default_factory=list)  # {time, text}
    confirmed_steps: list[str] = field(default_factory=list)
    created_at: str = ""

    def next_id(self, prefix: str, existing: list[str]) -> str:
        n = 1
        while f"{prefix}{n}" in existing:
            n += 1
        return f"{prefix}{n}"

    def objective(self, oid: str) -> Objective | None:
        for o in self.objectives:
            if o.id == oid:
                return o
        return None


def new_project(title: str, **kw) -> Project:
    return Project(id=uuid.uuid4().hex[:10], title=title,
                   created_at=time.strftime("%Y-%m-%d %H:%M"), **kw)


class ProjectStore:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def path(self, pid: str) -> str:
        return os.path.join(self.root, f"{pid}.json")

    def save(self, p: Project) -> str:
        with open(self.path(p.id), "w", encoding="utf-8") as f:
            json.dump(asdict(p), f, ensure_ascii=False, indent=1)
        return self.path(p.id)

    def load(self, pid: str) -> Project | None:
        path = self.path(pid)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return _project_from_dict(d)

    def list(self) -> list[dict]:
        out = []
        for name in sorted(os.listdir(self.root)):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(self.root, name), encoding="utf-8") as f:
                        d = json.load(f)
                    out.append({"id": d["id"], "title": d["title"],
                                "subject": d.get("subject", ""), "grade": d.get("grade", ""),
                                "created_at": d.get("created_at", "")})
                except Exception:
                    continue
        return out


def _project_from_dict(d: dict) -> Project:
    return Project(
        id=d["id"], title=d["title"], subject=d.get("subject", ""), grade=d.get("grade", ""),
        textbook=d.get("textbook", ""), unit=d.get("unit", ""),
        period_minutes=int(d.get("period_minutes", 45)),
        standards=d.get("standards", []),
        objectives=[Objective(**o) for o in d.get("objectives", [])],
        sections=[Section(**s) for s in d.get("sections", [])],
        exercises=[Exercise(**e) for e in d.get("exercises", [])],
        rubric=[RubricRow(**r) for r in d.get("rubric", [])],
        board=d.get("board", ""), reflections=d.get("reflections", []),
        confirmed_steps=d.get("confirmed_steps", []), created_at=d.get("created_at", ""),
    )
