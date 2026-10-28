"""本地教案工作台（标准库 http.server）。

五步共创：信息 → 目标 → 大纲 → 细化 → 材料 → 对齐校验 → 导出/反思。
每步可生成草案、在页面上编辑、确认锁定；知识库可在线添加语料。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .alignment import check_alignment
from .exporter import export_markdown
from .models import ProjectStore, _project_from_dict, new_project
from .workflow import Workflow, build_carryover

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LessonForge 教案工作台</title>
<style>
body{font-family:system-ui,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f4f5f7;color:#222}
header{background:#1f5fa8;color:#fff;padding:12px 18px;font-weight:700}
main{max-width:1060px;margin:0 auto;padding:14px}
.card{background:#fff;border-radius:12px;padding:14px 16px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
input,textarea,select{padding:7px 9px;border:1px solid #d5d9de;border-radius:8px;font-size:14px;width:100%;box-sizing:border-box}
button{background:#1f5fa8;color:#fff;border:0;border-radius:8px;padding:8px 14px;cursor:pointer;font-weight:600}
button.ghost{background:#e8ecf1;color:#333}
button.ok{background:#2e9e5b}
.row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1;min-width:120px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #eee;padding:6px;text-align:left;vertical-align:top}
.step{font-weight:700;margin:2px 0 8px}.badge{background:#eef4fb;border-radius:999px;padding:2px 10px;font-size:12px;color:#1f5fa8}
.small{color:#888;font-size:12px}.issue{color:#b03a2e}.good{color:#2e9e5b}
textarea{min-height:56px}
</style></head>
<body>
<header>📐 LessonForge 教案工作台 <span style="font-weight:400;font-size:13px">接地 · 分步共创 · 对齐校验</span></header>
<main>
<div class="card">
  <div class="row">
    <select id="plist" style="flex:2"></select>
    <button class="ghost" onclick="loadSelected()">打开</button>
    <button onclick="newProject()">新建课题</button>
  </div>
  <p class="small" id="kbinfo"></p>
  <details><summary class="small">往知识库加语料（教材/课标/教参文本，会存进 kb_library 并用于接地检索）</summary>
    <div class="row" style="margin-top:8px"><input id="kb_name" placeholder="文件名，如 教材-函数.txt" style="flex:1">
    <button class="ghost" onclick="addKb()">添加</button></div>
    <textarea id="kb_text" placeholder="粘贴文本…" style="margin-top:8px"></textarea>
  </details>
</div>

<div class="card" id="info_card">
  <div class="step">① 课题信息</div>
  <div class="row"><input id="f_title" placeholder="课题"><input id="f_subject" placeholder="学科"><input id="f_grade" placeholder="年级"></div>
  <div class="row" style="margin-top:8px"><input id="f_textbook" placeholder="教材版本，如 人教版八年级上册"><input id="f_unit" placeholder="单元"><input id="f_period" type="number" placeholder="课时分钟"></div>
  <textarea id="f_standards" placeholder="本课课标条目，一行一条" style="margin-top:8px"></textarea>
  <div style="margin-top:8px"><button class="ghost" onclick="saveInfo()">保存信息</button></div>
</div>

<div class="card"><div class="step">② 学习目标 <span class="badge" id="c_objectives"></span></div>
  <div id="objectives"></div>
  <div class="row" style="margin-top:8px"><button onclick="runStep('objectives')">生成目标草案</button>
  <button class="ok" onclick="confirmStep('objectives')">确认目标</button>
  <button class="ghost" onclick="saveEdits()">保存编辑</button></div>
</div>

<div class="card"><div class="step">③ 教学环节大纲 <span class="badge" id="c_outline"></span></div>
  <div id="sections"></div>
  <div class="row" style="margin-top:8px"><button onclick="runStep('outline')">生成大纲</button>
  <button class="ok" onclick="confirmStep('outline')">确认大纲</button>
  <button class="ghost" onclick="saveEdits()">保存编辑</button></div>
</div>

<div class="card"><div class="step">④ 环节细化（教师/学生活动 · 设计意图 · 分层任务）</div>
  <div id="details"></div>
  <div class="row" style="margin-top:8px"><button onclick="runStep('details')">生成细化</button>
  <button class="ghost" onclick="saveEdits()">保存编辑</button></div>
</div>

<div class="card"><div class="step">⑤ 材料：习题 · 评价量规 · 板书</div>
  <div id="materials"></div>
  <div class="row" style="margin-top:8px"><button onclick="runStep('materials')">生成材料</button>
  <button class="ghost" onclick="saveEdits()">保存编辑</button></div>
</div>

<div class="card"><div class="step">⑥ 对齐校验（目标 × 环节/习题/量规）</div>
  <div id="alignment">（保存后自动校验）</div>
</div>

<div class="card"><div class="step">⑦ 课后反思与导出</div>
  <textarea id="reflect" placeholder="这节课上完后的反思（会回流到同单元下一课的目标生成）"></textarea>
  <div class="row" style="margin-top:8px"><button class="ghost" onclick="addReflect()">存反思</button>
  <button onclick="exportMd()">导出教案 Markdown</button></div>
  <pre id="export_out" style="white-space:pre-wrap;background:#fafafa;border-radius:8px;padding:10px;max-height:300px;overflow:auto"></pre>
</div>
</main>
<script>
let P=null;
const $=id=>document.getElementById(id);
async function j(url,opt){const r=await fetch(url,opt);return r.json()}
async function loadList(){const d=await j('/api/projects');
  $('plist').innerHTML=d.projects.map(p=>`<option value="${p.id}">${p.title}（${p.subject} ${p.grade}）</option>`).join('')||'<option value="">（暂无工程）</option>';
  const kb=await j('/api/kb');$('kbinfo').textContent=`知识库：${kb.files.length} 个文件 / ${kb.chunks} 个片段 — ${kb.files.join('、')}`;}
async function openProject(id){if(!id)return;const d=await j('/api/project?id='+id);P=d.project;render();}
function loadSelected(){openProject($('plist').value)}
async function newProject(){const d=await j('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'新课题'})});await loadList();openProject(d.id)}
function fillInfo(){if(!P)return;$('f_title').value=P.title;$('f_subject').value=P.subject;$('f_grade').value=P.grade;
  $('f_textbook').value=P.textbook;$('f_unit').value=P.unit;$('f_period').value=P.period_minutes;
  $('f_standards').value=(P.standards||[]).join('\n');
  $('c_objectives').textContent=P.confirmed_steps.includes('objectives')?'已确认 ✓':'未确认';
  $('c_outline').textContent=P.confirmed_steps.includes('outline')?'已确认 ✓':'未确认';}
function collectInfo(){P.title=$('f_title').value;P.subject=$('f_subject').value;P.grade=$('f_grade').value;
  P.textbook=$('f_textbook').value;P.unit=$('f_unit').value;P.period_minutes=parseInt($('f_period').value||'45');
  P.standards=$('f_standards').value.split('\n').map(s=>s.trim()).filter(Boolean);}
async function saveInfo(){if(!P)return alert('先新建或打开一个工程');collectInfo();collectObjectives();collectSections();
  await j('/api/project/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(P)});openProject(P.id)}
async function saveEdits(){saveInfo()}
function render(){fillInfo();
  $('objectives').innerHTML=P.objectives.length?`<table><tr><th>ID</th><th>目标</th><th>维度</th><th>对应课标</th></tr>`+
    P.objectives.map((o,i)=>`<tr><td>${o.id}</td><td><input data-ob="text" data-i="${i}" value="${o.text.replace(/"/g,'&quot;')}"></td><td><input data-ob="dimension" data-i="${i}" value="${o.dimension}"></td><td><input data-ob="standard_ref" data-i="${i}" value="${(o.standard_ref||'').replace(/"/g,'&quot;')}"></td></tr>`).join('')+'</table>':'<p class="small">还没有目标，点「生成目标草案」。</p>';
  $('sections').innerHTML=P.sections.length?`<table><tr><th>ID</th><th>环节</th><th>分钟</th><th>承载目标ID（逗号）</th></tr>`+
    P.sections.map((s,i)=>`<tr><td>${s.id}</td><td><input data-sc="title" data-i="${i}" value="${s.title.replace(/"/g,'&quot;')}"></td><td><input data-sc="minutes" data-i="${i}" type="number" value="${s.minutes}" style="width:70px"></td><td><input data-sc="objective_ids" data-i="${i}" value="${(s.objective_ids||[]).join(',')}"></td></tr>`).join('')+'</table>':'<p class="small">还没有大纲。</p>';
  $('details').innerHTML=P.sections.map((s,i)=>`<div style="border-top:1px dashed #ddd;padding:8px 0"><b>${s.id}《${s.title}》</b>
    <textarea data-dt="teacher_activity" data-i="${i}" placeholder="教师活动">${s.teacher_activity||''}</textarea>
    <textarea data-dt="student_activity" data-i="${i}" placeholder="学生活动">${s.student_activity||''}</textarea>
    <textarea data-dt="intent" data-i="${i}" placeholder="设计意图">${s.intent||''}</textarea>
    <div class="row"><input data-lv="基础" data-i="${i}" placeholder="基础层任务" value="${(s.levels||{})['基础']||''}">
    <input data-lv="提高" data-i="${i}" placeholder="提高层任务" value="${(s.levels||{})['提高']||''}">
    <input data-lv="挑战" data-i="${i}" placeholder="挑战层任务" value="${(s.levels||{})['挑战']||''}"></div></div>`).join('')||'<p class="small">先有大纲再细化。</p>';
  $('materials').innerHTML=(P.exercises.length?`<table><tr><th>ID</th><th>层级</th><th>题目</th><th>目标</th></tr>`+
    P.exercises.map(e=>`<tr><td>${e.id}</td><td>${e.level}</td><td>${e.stem}</td><td>${e.objective_id}</td></tr>`).join('')+'</table>':'<p class="small">还没有习题。</p>')+
    (P.rubric.length?`<p class="small">量规 ${P.rubric.length} 行（按目标生成）。</p>`:'')+
    `<textarea id="board" placeholder="板书设计">${P.board||''}</textarea>`;
  renderAlignment();}
function collectObjectives(){document.querySelectorAll('[data-ob]').forEach(el=>{const o=P.objectives[+el.dataset.i];if(o)o[el.dataset.ob]=el.value})}
function collectSections(){document.querySelectorAll('[data-sc]').forEach(el=>{const s=P.sections[+el.dataset.i];if(!s)return;
    if(el.dataset.sc==='objective_ids')s.objective_ids=el.value.split(',').map(x=>x.trim()).filter(Boolean);
    else if(el.dataset.sc==='minutes')s.minutes=parseInt(el.value||'0');else s[el.dataset.sc]=el.value});
  document.querySelectorAll('[data-dt]').forEach(el=>{const s=P.sections[+el.dataset.i];if(s)s[el.dataset.dt]=el.value});
  document.querySelectorAll('[data-lv]').forEach(el=>{const s=P.sections[+el.dataset.i];if(s){s.levels=s.levels||{};s.levels[el.dataset.lv]=el.value}});
  const b=$('board');if(b)P.board=b.value;}
async function renderAlignment(){if(!P)return;const d=await j('/api/project?id='+P.id);
  const a=d.alignment;
  $('alignment').innerHTML=`<p>覆盖率 <b>${a.coverage_pct}%</b> · 环节总时长 ${a.total_minutes} 分钟 ${a.time_ok?'<span class="good">✓</span>':'<span class="issue">与课时不符</span>'}</p>`+
   `<table><tr><th>目标</th><th>环节</th><th>习题</th><th>量规</th><th>贯通</th></tr>`+
   a.matrix.map(m=>`<tr><td>${m.objective_id}</td><td>${m.sections.join(',')||'—'}</td><td>${m.exercises.join(',')||'—'}</td><td>${m.rubric?'✓':'—'}</td><td>${m.covered?'<span class="good">✓</span>':'<span class="issue">缺口</span>'}</td></tr>`).join('')+'</table>'+
   (a.issues.length?'<ul>'+a.issues.map(i=>`<li class="issue">${i}</li>`).join('')+'</ul>':'<p class="good">全部贯通，没有缺口 ✓</p>');}
async function runStep(step){if(!P)return alert('先新建或打开工程');await saveInfo();
  const d=await j('/api/step',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:P.id,step})});
  if(d.error)return alert(d.error);P=d.project;render();}
async function confirmStep(step){await saveInfo();await j('/api/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:P.id,step})});openProject(P.id)}
async function addReflect(){if(!P)return;const t=$('reflect').value.trim();if(!t)return;
  await j('/api/reflect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:P.id,text:t})});$('reflect').value='';alert('反思已存档，将回流到同单元下一课');openProject(P.id)}
async function addKb(){const name=$('kb_name').value.trim(),text=$('kb_text').value.trim();if(!name||!text)return alert('文件名和内容都要填');
  await j('/api/kb/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,text})});$('kb_name').value='';$('kb_text').value='';loadList()}
async function exportMd(){if(!P)return;const r=await fetch('/api/export?id='+P.id);$('export_out').textContent=await r.text();}
(async()=>{await loadList();const first=$('plist').value;if(first)openProject(first)})();
</script>
</body></html>"""


class Workbench:
    def __init__(self, store: ProjectStore, workflow: Workflow, kb_dir: str):
        self.store = store
        self.workflow = workflow
        self.kb_dir = kb_dir

    def _prev_in_unit(self, p) -> object | None:
        candidates = []
        for meta in self.store.list():
            if meta["id"] == p.id:
                continue
            other = self.store.load(meta["id"])
            if other and other.unit and other.unit == p.unit:
                candidates.append(other)
        candidates.sort(key=lambda x: x.created_at)
        return candidates[-1] if candidates else None

    def serve(self, host: str = "127.0.0.1", port: int = 8770):
        wb = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj, code=200):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    return json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    return {}

            def _project_json(self, p):
                return {"project": json.loads(json.dumps(asdict(p), ensure_ascii=False)),
                        "alignment": check_alignment(p)}

            def do_GET(self):
                if self.path == "/":
                    body = HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path.startswith("/api/projects"):
                    self._json({"projects": wb.store.list()})
                elif self.path.startswith("/api/kb"):
                    kb = wb.workflow.kb
                    self._json(kb.stats() if kb else {"files": [], "chunks": 0})
                elif self.path.startswith("/api/project"):
                    pid = self.path.split("id=")[1].split("&")[0] if "id=" in self.path else ""
                    p = wb.store.load(pid)
                    if not p:
                        self._json({"error": "工程不存在"}, 404)
                    else:
                        self._json(self._project_json(p))
                elif self.path.startswith("/api/export"):
                    pid = self.path.split("id=")[1].split("&")[0] if "id=" in self.path else ""
                    p = wb.store.load(pid)
                    if not p:
                        self._json({"error": "工程不存在"}, 404)
                    else:
                        body = export_markdown(p).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/markdown; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                else:
                    self._json({"error": "not found"}, 404)

            def do_POST(self):
                data = self._body()
                if self.path == "/api/projects":
                    p = new_project(str(data.get("title") or "新课题"),
                                    subject=str(data.get("subject", "")),
                                    grade=str(data.get("grade", "")),
                                    textbook=str(data.get("textbook", "")),
                                    unit=str(data.get("unit", "")))
                    wb.store.save(p)
                    self._json({"id": p.id})
                elif self.path == "/api/project/save":
                    try:
                        p = _project_from_dict(data)
                    except Exception as e:
                        self._json({"error": f"工程数据不合法：{e}"}, 400)
                        return
                    wb.store.save(p)
                    self._json(self._project_json(p))
                elif self.path == "/api/step":
                    p = wb.store.load(str(data.get("id", "")))
                    if not p:
                        self._json({"error": "工程不存在"}, 404)
                        return
                    step = str(data.get("step", ""))
                    wf = wb.workflow
                    if step == "objectives":
                        carry = build_carryover(wb._prev_in_unit(p))
                        p.objectives = wf.gen_objectives(p, carryover=carry)
                    elif step == "outline":
                        p.sections = wf.gen_outline(p)
                    elif step == "details":
                        p.sections = wf.gen_details(p)
                    elif step == "materials":
                        p.exercises, p.rubric, p.board = wf.gen_materials(p)
                    else:
                        self._json({"error": "未知步骤"}, 400)
                        return
                    wb.store.save(p)
                    self._json(self._project_json(p))
                elif self.path == "/api/confirm":
                    p = wb.store.load(str(data.get("id", "")))
                    if not p:
                        self._json({"error": "工程不存在"}, 404)
                        return
                    step = str(data.get("step", ""))
                    if step and step not in p.confirmed_steps:
                        p.confirmed_steps.append(step)
                    wb.store.save(p)
                    self._json(self._project_json(p))
                elif self.path == "/api/reflect":
                    p = wb.store.load(str(data.get("id", "")))
                    if not p:
                        self._json({"error": "工程不存在"}, 404)
                        return
                    text = str(data.get("text", "")).strip()
                    if text:
                        p.reflections.append({"time": time.strftime("%Y-%m-%d %H:%M"), "text": text})
                        wb.store.save(p)
                    self._json(self._project_json(p))
                elif self.path == "/api/kb/add":
                    name = os.path.basename(str(data.get("name", "kb.txt")))
                    text = str(data.get("text", ""))
                    if not name or not text:
                        self._json({"error": "文件名与内容必填"}, 400)
                        return
                    os.makedirs(wb.kb_dir, exist_ok=True)
                    with open(os.path.join(wb.kb_dir, name), "w", encoding="utf-8") as f:
                        f.write(text)
                    if wb.workflow.kb:
                        wb.workflow.kb.add_text(name, text)
                    self._json({"ok": True})
                else:
                    self._json({"error": "not found"}, 404)

        server = ThreadingHTTPServer((host, port), H)
        print(f"教案工作台已启动：http://{host}:{port} （Ctrl+C 退出）")
        server.serve_forever()
