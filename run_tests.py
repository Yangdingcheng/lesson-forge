#!/usr/bin/env python3
"""核心逻辑测试（纯标准库）：python run_tests.py"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.dirname(os.path.abspath(__file__))

from lesson_forge.alignment import check_alignment
from lesson_forge.exporter import export_markdown
from lesson_forge.kb import KnowledgeBase
from lesson_forge.models import Exercise, Objective, Project, ProjectStore, RubricRow, Section, new_project
from lesson_forge.remix import parse_old_plan
from lesson_forge.workflow import Workflow, build_carryover

PASS = []
def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("✅" if cond else "❌"), name)
    assert cond, name

# ---------- KB ----------
kb = KnowledgeBase()
n = kb.load_dir(os.path.join(BASE, "samples", "kb"))
check("知识库-加载示例语料", n == 3 and kb.stats()["chunks"] >= 3)
hits = kb.search("勾股定理 赵爽弦图 证明", k=3)
check("知识库-检索命中", len(hits) > 0)
check("知识库-引用格式", hits and hits[0]["cite"].startswith("[来源:"))
ctx = kb.context_block("逆定理 判断直角三角形")
check("知识库-上下文块", "来源" in ctx)

# ---------- 对齐校验 ----------
def bare_project() -> Project:
    return Project(id="t1", title="测试课", subject="数学", period_minutes=45,
                   standards=["标准A", "标准B"])

p = bare_project()
p.objectives = [Objective("G1", "目标一", standard_ref="标准A"),
                Objective("G2", "目标二", standard_ref="标准B")]
p.sections = [Section("S1", "导入", 10, ["G1"]), Section("S2", "练习", 20, [])]
p.exercises = [Exercise("E1", "题一", objective_id="G1"), Exercise("E2", "题二", objective_id="G9")]
p.rubric = [RubricRow("G1")]
rep = check_alignment(p)
check("对齐-孤儿目标", rep["orphan_objectives"] == ["G2"])
check("对齐-野习题", rep["wild_exercises"] == ["E2"])
check("对齐-裸环节", rep["bare_sections"] == ["S2"])
check("对齐-量规缺口", rep["rubric_missing"] == ["G2"])
check("对齐-时间核账", rep["time_ok"] is False and rep["total_minutes"] == 30)
check("对齐-覆盖率", rep["coverage_pct"] == 50)

# ---------- 工作流（模板模式） ----------
wf = Workflow(ai=None, kb=kb)
p2 = new_project("勾股定理（第 1 课时）", subject="数学", grade="八年级",
                 textbook="人教版", unit="勾股定理", period_minutes=45,
                 standards=["探索并证明勾股定理", "经历观察猜想验证的过程", "掌握勾股定理的逆定理"])
p2.objectives = wf.gen_objectives(p2)
check("工作流-目标生成", len(p2.objectives) == 3 and all(o.standard_ref for o in p2.objectives))
p2.sections = wf.gen_outline(p2)
check("工作流-大纲时长对齐", sum(s.minutes for s in p2.sections) == 45)
check("工作流-大纲目标贯通", all(any(o.id in s.objective_ids for s in p2.sections) for o in p2.objectives))
p2.sections = wf.gen_details(p2)
check("工作流-细化含分层", all(s.levels.get("基础") and s.teacher_activity for s in p2.sections))
p2.exercises, p2.rubric, p2.board = wf.gen_materials(p2)
check("工作流-材料齐全", len(p2.exercises) == 9 and len(p2.rubric) == 3 and bool(p2.board))
rep2 = check_alignment(p2)
check("工作流-模板产物对齐通过", rep2["ok"] and rep2["coverage_pct"] == 100)

# ---------- 回流 ----------
p2.reflections.append({"time": "2026-10-28", "text": "学生普遍把斜边认错"})
carry = build_carryover(p2)
check("回流-反思进入上下文", "斜边认错" in carry)

# ---------- 旧教案改造 ----------
old = open(os.path.join(BASE, "samples", "old_plan.txt"), encoding="utf-8").read()
rp, notes = parse_old_plan(old, subject="数学")
check("改造-目标解析", len(rp.objectives) == 3)
check("改造-环节解析", len(rp.sections) == 5)
check("改造-缺口提示", len(notes) >= 3)
rep3 = check_alignment(rp)
check("改造-缺口被校验发现", len(rep3["issues"]) >= 3)

# ---------- 导出与存储 ----------
md = export_markdown(p2)
check("导出-含目标与量规", "学习目标" in md and "评价量规" in md and "G1" in md)
store = ProjectStore(tempfile.mkdtemp())
store.save(p2)
back = store.load(p2.id)
check("存储-往返一致", back is not None and back.title == p2.title and len(back.exercises) == 9)

# ---------- 工作台 smoke ----------
proc = subprocess.Popen([sys.executable, "main.py", "--web", "--port", "8771"],
                        cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    ok = False
    for _ in range(40):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8771/", timeout=2) as resp:
                html = resp.read().decode("utf-8")
            ok = "教案工作台" in html
            break
        except Exception:
            time.sleep(0.25)
    check("工作台-首页", ok)
    req = urllib.request.Request("http://127.0.0.1:8771/api/projects", data=b"{}",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        pid = json.loads(resp.read())["id"]
    check("工作台-建工程", bool(pid))
finally:
    proc.terminate()

print(f"\n全部 {len(PASS)} 项测试通过 ✅" if all(c for _, c in PASS) else "\n存在失败 ❌")
