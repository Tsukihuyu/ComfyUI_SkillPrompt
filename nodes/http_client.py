"""Minimal OpenAI-compatible chat client (stdlib only).

Works with llama.cpp server, LM Studio, Ollama (/v1), vLLM, DeepSeek, OpenAI,
SiliconFlow, and anything else that speaks ``/v1/chat/completions``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple


def endpoint_url(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise ValueError(
            "base_url 为空。填一个 OpenAI 兼容端点，例如：\n"
            "  Ollama        http://127.0.0.1:11434/v1\n"
            "  LM Studio     http://127.0.0.1:1234/v1\n"
            "  llama.cpp     http://127.0.0.1:8080/v1\n"
            "  DeepSeek      https://api.deepseek.com/v1"
        )
    if url.endswith("/chat/completions"):
        return url
    if not url.endswith("/v1"):
        url += "/v1"
    return url + "/chat/completions"


def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.5,
    top_p: float = 0.9,
    max_tokens: int = 2048,
    timeout: int = 600,
) -> Tuple[str, Optional[Dict]]:
    """POST /chat/completions and return ``(text, usage)``."""
    if not (model or "").strip():
        raise ValueError("model 为空：填服务端实际暴露的模型名（本地端点可以先 curl /v1/models 看一眼）。")

    url = endpoint_url(base_url)
    payload = {
        "model": model.strip(),
        "messages": messages,
        "temperature": float(temperature),
        "top_p": float(top_p),
        "max_tokens": int(max_tokens),
        "stream": False,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=int(timeout)) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        raise RuntimeError(f"HTTP {e.code} from {url}\n{detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"连不上 {url}：{e.reason}\n"
            "检查服务是否已启动、端口是否正确、防火墙是否放行。"
        ) from e
    except TimeoutError as e:
        raise RuntimeError(f"请求超时（{timeout}s）：{url}") from e

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"返回内容不是 JSON：{body[:500]}")

    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError(f"返回里没有 choices：{body[:500]}")
    message = choices[0].get("message") or {}
    text = message.get("content")
    if text is None:
        text = message.get("reasoning_content") or ""
    if not isinstance(text, str) or not text.strip():
        finish = choices[0].get("finish_reason")
        raise RuntimeError(f"模型返回空内容（finish_reason={finish}）：{body[:500]}")

    return text, {**(result.get("usage") or {}), "finish_reason": choices[0].get("finish_reason")}
