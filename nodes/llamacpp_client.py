"""Optional in-process llama.cpp backend (llama-cpp-python).

Nothing here is imported eagerly: if ``llama_cpp`` is not installed the node
falls back to the HTTP backend and reports a clear install hint. Models are
cached per (path, n_ctx, n_gpu_layers, chat_format) so repeated runs do not
reload 20 GB of weights.
"""

from __future__ import annotations

import gc
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_LOCK = threading.Lock()
_MODELS: Dict[Tuple, object] = {}
ENV_GGUF_DIRS = "SKILLPROMPT_GGUF_DIRS"
PLACEHOLDER = "(no .gguf found - put models under ComfyUI/models/LLM/)"


def available() -> bool:
    try:
        import llama_cpp  # noqa: F401
        return True
    except Exception:
        return False


def _model_dirs() -> List[Path]:
    dirs: List[Path] = []
    try:  # inside ComfyUI
        import folder_paths  # type: ignore

        models_dir = getattr(folder_paths, "models_dir", None)
        if models_dir:
            dirs.append(Path(models_dir))
        for key in ("LLM", "llm", "GGUF", "gguf"):
            try:
                for p in folder_paths.get_folder_paths(key):
                    dirs.append(Path(p))
            except Exception:
                continue
    except Exception:
        pass

    extra = os.environ.get(ENV_GGUF_DIRS, "")
    for raw in extra.split(os.pathsep):
        raw = raw.strip()
        if raw:
            dirs.append(Path(raw))

    seen, out = set(), []
    for d in dirs:
        key = str(d).lower()
        if key not in seen and d.is_dir():
            seen.add(key)
            out.append(d)
    return out


def list_gguf_models() -> List[str]:
    """Relative names of every .gguf file found in the configured folders."""
    found: Dict[str, str] = {}
    for base in _model_dirs():
        try:
            files = sorted(base.rglob("*.gguf"))
        except OSError:
            continue
        for f in files:
            try:
                rel = f.relative_to(base)
            except ValueError:
                rel = Path(f.name)
            name = str(rel).replace("\\", "/")
            found.setdefault(name, str(f))
    return sorted(found.keys()) or [PLACEHOLDER]


def resolve_model(name: str) -> Path:
    for base in _model_dirs():
        candidate = base / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"找不到 GGUF 模型「{name}」。可选目录：{', '.join(str(d) for d in _model_dirs()) or '（无）'}\n"
        f"也可以用环境变量 {ENV_GGUF_DIRS} 指定额外目录。"
    )


def _load(model_name: str, n_ctx: int, n_gpu_layers: int, chat_format: str):
    from llama_cpp import Llama  # raises ImportError with a clear traceback

    key = (model_name, int(n_ctx), int(n_gpu_layers), chat_format or "")
    with _LOCK:
        inst = _MODELS.get(key)
    if inst is not None:
        return inst

    path = resolve_model(model_name)
    kwargs = dict(
        model_path=str(path),
        n_ctx=int(n_ctx),
        n_gpu_layers=int(n_gpu_layers),
        verbose=False,
    )
    if chat_format:
        kwargs["chat_format"] = chat_format
    inst = Llama(**kwargs)
    with _LOCK:
        _MODELS[key] = inst
    return inst


def chat_completion(
    model_name: str,
    messages: List[Dict[str, str]],
    n_ctx: int = 32768,
    n_gpu_layers: int = -1,
    chat_format: str = "",
    temperature: float = 0.5,
    top_p: float = 0.9,
    max_tokens: int = 2048,
    seed: int = -1,
    keep_model_loaded: bool = True,
) -> Tuple[str, Optional[Dict]]:
    if not available():
        raise RuntimeError(
            "内置 llama.cpp 后端不可用：没有安装 llama-cpp-python。\n"
            "安装示例（Windows，需与本机 CUDA 匹配的 wheel）：\n"
            "  pip install llama-cpp-python --extra-index-url "
            "https://abetlen.github.io/llama-cpp-python/whl/cu124\n"
            "或者把 backend 切到 http，用 LM Studio / llama-server / Ollama。"
        )
    if model_name == PLACEHOLDER:
        raise ValueError(
            f"没有找到可用的 .gguf 模型。把模型放进 ComfyUI/models/LLM/，"
            f"或设置环境变量 {ENV_GGUF_DIRS} 指向模型目录。"
        )

    inst = _load(model_name, n_ctx, n_gpu_layers, chat_format)
    try:
        out = inst.create_chat_completion(
            messages=messages,
            temperature=float(temperature),
            top_p=float(top_p),
            max_tokens=int(max_tokens),
            seed=int(seed),
        )
    finally:
        if not keep_model_loaded:
            unload_all()

    choices = (out or {}).get("choices") or []
    if not choices:
        raise RuntimeError(f"llama.cpp 返回里没有 choices：{str(out)[:400]}")
    text = (choices[0].get("message") or {}).get("content") or ""
    if not text.strip():
        raise RuntimeError(f"llama.cpp 返回空内容（finish_reason={choices[0].get('finish_reason')}）")
    return text, (out or {}).get("usage")


def unload_all() -> None:
    with _LOCK:
        models = list(_MODELS.values())
        _MODELS.clear()
    for inst in models:
        try:
            del inst
        except Exception:
            pass
    gc.collect()
    try:  # inside ComfyUI: be a good citizen about VRAM
        import comfy.model_management as mm  # type: ignore

        mm.soft_empty_cache()
    except Exception:
        pass


def loaded_models() -> List[str]:
    with _LOCK:
        return [k[0] for k in _MODELS.keys()]
