"""本地知识库（接地层）：把教材、课标、教参文本切块入库，生成时检索注入并给出来源。

纯标准库 BM25：中文用字符二元组 + 英文单词切分，对短文本教育语料足够稳，
且不需要向量模型与任何第三方依赖。引用格式：[来源: 文件名 · 第N块]。
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for m in re.finditer(r"[a-zA-Z0-9]+", text.lower()):
        tokens.append(m.group(0))
    zh = re.findall(r"[一-鿿]", text)
    tokens.extend(zh)
    tokens.extend(a + b for a, b in zip(zh, zh[1:]))
    return tokens


def chunk_text(text: str, size: int = 320, overlap: int = 60) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) <= size:
            buf = (buf + "\n" + p) if buf else p
        else:
            if buf:
                chunks.append(buf)
            while len(p) > size:
                chunks.append(p[:size])
                p = p[size - overlap:]
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


class KnowledgeBase:
    def __init__(self):
        self.docs: list[dict] = []   # {file, idx, text, tf, len}
        self._df: Counter = Counter()
        self._avgdl: float = 0.0

    def add_text(self, filename: str, text: str):
        for i, chunk in enumerate(chunk_text(text)):
            tf = Counter(tokenize(chunk))
            self.docs.append({"file": filename, "idx": i + 1, "text": chunk,
                              "tf": tf, "len": sum(tf.values()) or 1})
            for term in tf:
                self._df[term] += 1
        self._recalc()

    def add_file(self, path: str):
        with open(path, encoding="utf-8", errors="ignore") as f:
            self.add_text(os.path.basename(path), f.read())

    def load_dir(self, folder: str) -> int:
        n = 0
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                if name.lower().endswith((".txt", ".md")):
                    self.add_file(os.path.join(folder, name))
                    n += 1
        return n

    def _recalc(self):
        if self.docs:
            self._avgdl = sum(d["len"] for d in self.docs) / len(self.docs)

    def search(self, query: str, k: int = 5) -> list[dict]:
        if not self.docs:
            return []
        qterms = tokenize(query)
        n_docs = len(self.docs)
        k1, b = 1.5, 0.75
        scored = []
        for d in self.docs:
            score = 0.0
            for t in qterms:
                if t not in d["tf"]:
                    continue
                df = self._df.get(t, 0)
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                f = d["tf"][t]
                score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * d["len"] / (self._avgdl or 1)))
            if score > 0:
                scored.append((score, d))
        scored.sort(key=lambda x: -x[0])
        return [{"file": d["file"], "idx": d["idx"], "text": d["text"],
                 "score": round(s, 3),
                 "cite": f"[来源: {d['file']} · 第{d['idx']}块]"}
                for s, d in scored[:k]]

    def context_block(self, query: str, k: int = 5) -> str:
        hits = self.search(query, k)
        if not hits:
            return ""
        lines = ["以下是从本地教材/课标知识库检索到的相关材料，生成时应以其为准并标注来源："]
        for h in hits:
            lines.append(f"{h['cite']}\n{h['text']}")
        return "\n".join(lines)

    def stats(self) -> dict:
        files = sorted({d["file"] for d in self.docs})
        return {"files": files, "chunks": len(self.docs)}
