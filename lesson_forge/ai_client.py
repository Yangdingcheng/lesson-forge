"""OpenAI 兼容 AI 客户端（标准库）+ 宽松 JSON 提取。"""

from __future__ import annotations

import json
import re
import urllib.request


class AIClient:
    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.6, timeout: int = 60):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.temperature = temperature
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def chat(self, system: str, user: str) -> str:
        if not self.available():
            return ""
        payload = {"model": self.model, "temperature": self.temperature,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return str(data["choices"][0]["message"]["content"]).strip()
        except Exception:
            return ""


def extract_json(text: str):
    """从模型回复里提取 JSON（容忍代码围栏与前后缀文字）。失败返回 None。"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = t.find(opener), t.rfind(closer)
        if 0 <= i < j:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    return None
