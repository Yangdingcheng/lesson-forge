#!/usr/bin/env python3
"""LessonForge 教案工作台 · 入口

用法：
  python main.py --demo            离线全流程演示（勾股定理：五步共创 + 对齐校验 + 导出 + 旧教案改造）
  python main.py --web [--port 8770]   打开本地工作台
  python main.py --remix samples/old_plan.txt   把旧教案解析成工程并报告缺口

配置：复制 config.example.json 为 config.json，填上 AI 的 base_url / api_key / model（不填则走模板模式）。
知识库：把教材/课标/教参的 txt/md 放进 kb_library/ 目录即可。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lesson_forge.ai_client import AIClient
from lesson_forge.alignment import check_alignment
from lesson_forge.exporter import export_markdown
from lesson_forge.kb import KnowledgeBase
from lesson_forge.models import ProjectStore, new_project
from lesson_forge.remix import parse_old_plan
from lesson_forge.workflow import Workflow

BASE = os.path.dirname(os.path.abspath(__file__))

DEMO_STANDARDS = [
    "探索并证明勾股定理，能运用勾股定理解决简单实际问题（示例课标条目）",
    "经历观察、猜想、验证的过程，发展几何直观与推理能力（示例课标条目）",
    "掌握勾股定理的逆定理，能判断一个三角形是否为直角三角形（示例课标条目）",
]


def load_config() -> dict:
    for name in ("config.json", "config.example.json"):
        p = os.path.join(BASE, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return {}


def build_workflow(cfg: dict, extra_kb_dirs=None):
    kb = KnowledgeBase()
    dirs = [os.path.join(BASE, "kb_library")] + list(extra_kb_dirs or [])
    for d in dirs:
        kb.load_dir(d)
    ai_cfg = cfg.get("ai", {})
    ai = AIClient(ai_cfg.get("base_url", ""), ai_cfg.get("api_key", ""), ai_cfg.get("model", ""),
                  temperature=float(ai_cfg.get("temperature", 0.6)))
    return Workflow(ai=ai, kb=kb), kb


def run_demo(cfg: dict):
    wf, kb = build_workflow(cfg, extra_kb_dirs=[os.path.join(BASE, "samples", "kb")])
    mode = "AI 模式" if (wf.ai and wf.ai.available()) else "模板模式（未配置 API Key）"
    print("=" * 64)
    print(f"LessonForge 离线演示 · {mode} · 知识库 {kb.stats()['chunks']} 个片段")
    print("=" * 64)
    store = ProjectStore(os.path.join(BASE, "data", "projects"))
    p = new_project("勾股定理（第 1 课时）", subject="数学", grade="八年级",
                    textbook="人教版八年级下册（示例）", unit="勾股定理",
                    period_minutes=45, standards=list(DEMO_STANDARDS))

    p.objectives = wf.gen_objectives(p)
    print(f"\n[步骤1 · 学习目标] {len(p.objectives)} 条")
    for o in p.objectives:
        print(f"  {o.id} [{o.dimension}] {o.text[:52]}")
    p.sections = wf.gen_outline(p)
    print(f"\n[步骤2 · 环节大纲] 总时长 {sum(s.minutes for s in p.sections)} 分钟")
    for s in p.sections:
        print(f"  {s.id} {s.title} {s.minutes} 分钟 -> 目标 {','.join(s.objective_ids)}")
    p.sections = wf.gen_details(p)
    print("\n[步骤3 · 环节细化] 已生成教师/学生活动、设计意图与三层任务（节选）")
    s0 = p.sections[1] if len(p.sections) > 1 else p.sections[0]
    print(f"  {s0.id} {s0.title} 学生活动：{s0.student_activity[:60]}")
    p.exercises, p.rubric, p.board = wf.gen_materials(p)
    print(f"\n[步骤4 · 材料] 习题 {len(p.exercises)} 道（每目标 基础/提高/挑战 各一）· 量规 {len(p.rubric)} 行 · 板书已生成")
    rep = check_alignment(p)
    print(f"\n[步骤5 · 对齐校验] 覆盖率 {rep['coverage_pct']}% · 问题 {len(rep['issues'])} 个")
    for i in rep["issues"]:
        print(f"  ! {i}")
    if rep["ok"]:
        print("  OK 目标-活动-评价全部贯通")
    p.confirmed_steps = ["objectives", "outline"]
    store.save(p)
    out_dir = os.path.join(BASE, "exports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "demo-gougu.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(export_markdown(p))
    print(f"\n教案已导出：exports/demo-gougu.md（工程 ID {p.id}，已存入 data/projects）")

    print("\n" + "-" * 64)
    print("旧教案改造演示：samples/old_plan.txt")
    old_text = open(os.path.join(BASE, "samples", "old_plan.txt"), encoding="utf-8").read()
    rp, notes = parse_old_plan(old_text, subject="数学", grade="八年级")
    print(f"解析出：目标 {len(rp.objectives)} 条 · 环节 {len(rp.sections)} 个 · 板书 {'有' if rp.board else '无'}")
    for n in notes:
        print(f"  - {n}")
    rep2 = check_alignment(rp)
    print(f"对齐校验发现 {len(rep2['issues'])} 个缺口（旧教案的通病，一次列清）：")
    for i in rep2["issues"][:8]:
        print(f"  ! {i}")


def main():
    ap = argparse.ArgumentParser(description="LessonForge 教案工作台")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--web", action="store_true")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--remix", type=str, default="", help="旧教案文本路径")
    args = ap.parse_args()
    cfg = load_config()

    if args.demo:
        run_demo(cfg)
    elif args.remix:
        text = open(args.remix, encoding="utf-8").read()
        p, notes = parse_old_plan(text)
        store = ProjectStore(os.path.join(BASE, "data", "projects"))
        store.save(p)
        print(f"已解析为工程 {p.title}（ID {p.id}）：目标 {len(p.objectives)} · 环节 {len(p.sections)}")
        for n in notes:
            print(f"  - {n}")
        rep = check_alignment(p)
        print(f"对齐缺口 {len(rep['issues'])} 个：")
        for i in rep["issues"]:
            print(f"  ! {i}")
        print("打开 --web 工作台即可逐项补齐。")
    elif args.web:
        from lesson_forge.webui import Workbench
        wf, kb = build_workflow(cfg)
        print(f"知识库：{kb.stats()['files']}（{kb.stats()['chunks']} 个片段）")
        store = ProjectStore(os.path.join(BASE, "data", "projects"))
        Workbench(store, wf, os.path.join(BASE, "kb_library")).serve(port=args.port)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
