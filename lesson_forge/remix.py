"""旧教案改造：把一份现成教案文本解析成结构化工程，并指出缺口。

教师的高频需求是「改旧教案」而非白纸创作——解析后直接跑对齐校验，
缺评价、缺课标、目标没人承载等问题一次列清，再在工作台里逐步补齐。
"""

from __future__ import annotations

import re

from .models import Objective, Project, Section, new_project

_OBJ_HEADS = ("教学目标", "学习目标", "教学目的", "目标")
_PROC_HEADS = ("教学过程", "教学环节", "教学流程", "教学步骤")
_BOARD_HEADS = ("板书设计", "板书")
_SECTION_WORDS = ("导入", "新课", "探究", "讲解", "例题", "练习", "巩固", "小结", "总结", "作业", "拓展", "复习", "情境")
_STOP_HEADS = ("教学重点", "教学难点", "教学准备", "学情分析", "教材分析", "教学方法", "教学反思", "设计意图")


def _clean(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^[0-9]+[、．.]\s*", "", s)
    s = re.sub(r"^第[一二三四五六七八九十]+[、．.]\s*", "", s)
    return s.strip(" -*·•")


def parse_old_plan(text: str, subject: str = "", grade: str = "") -> tuple[Project, list[str]]:
    notes: list[str] = []
    lines = [ln.rstrip() for ln in text.splitlines()]
    title = ""
    for ln in lines[:6]:
        s = ln.strip().strip("# ").strip()
        if s:
            m = re.search(r"课题[:：]\s*(.+)", s)
            title = (m.group(1) if m else s)[:40]
            break
    p = new_project(title or "未命名课题", subject=subject, grade=grade)

    mode = ""
    obj_lines: list[str] = []
    proc_lines: list[str] = []
    board_lines: list[str] = []
    for ln in lines:
        s = ln.strip()
        head = s.strip("# ").strip()
        if any(head.startswith(h) for h in _OBJ_HEADS) and len(head) <= 8:
            mode = "obj"
            continue
        if any(head.startswith(h) for h in _PROC_HEADS) and len(head) <= 8:
            mode = "proc"
            continue
        if any(head.startswith(h) for h in _BOARD_HEADS) and len(head) <= 8:
            mode = "board"
            continue
        if any(head.startswith(h) for h in _STOP_HEADS) and len(head) <= 8:
            mode = ""
            continue
        if mode == "obj" and s:
            obj_lines.append(s)
        elif mode == "proc" and s:
            proc_lines.append(s)
        elif mode == "board" and s:
            board_lines.append(s)

    for i, raw in enumerate(obj_lines[:6], 1):
        t = _clean(raw)
        if t:
            p.objectives.append(Objective(id=f"G{i}", text=t))
    if not p.objectives:
        notes.append("旧教案里没有解析出明确的学习目标（需要补写并绑定课标）。")

    current: Section | None = None
    for raw in proc_lines:
        s = _clean(raw)
        if not s:
            continue
        is_head = (len(s) <= 14 and any(w in s for w in _SECTION_WORDS)) or \
            bool(re.match(r"^(环节|第[一二三四五六七八九十]+)", raw.strip()))
        if is_head:
            current = Section(id=f"S{len(p.sections) + 1}", title=s[:20], minutes=0)
            p.sections.append(current)
        elif current is not None:
            current.teacher_activity = (current.teacher_activity + "\n" + s).strip()
        else:
            current = Section(id="S1", title="教学过程", minutes=0, teacher_activity=s)
            p.sections.append(current)
    if p.sections:
        each = max(3, p.period_minutes // len(p.sections))
        for s in p.sections:
            s.minutes = each
        notes.append(f"从旧教案解析出 {len(p.sections)} 个环节，时长为均分估算，请在工作台校准。")
    else:
        notes.append("旧教案里没有解析出教学环节。")
    if board_lines:
        p.board = "\n".join(board_lines)
    else:
        notes.append("旧教案没有板书设计（可在材料步骤生成）。")
    notes.append("旧教案通常没有结构化习题与评价量规：请在「材料」步骤生成，生成后习题会自动绑定目标。")
    notes.append("旧教案未标注课标条目：请在工程信息里补上本课课标，目标的课标引用也可逐条补齐。")
    return p, notes
