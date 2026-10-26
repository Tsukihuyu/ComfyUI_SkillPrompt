"""SkillPrompt optimizer nodes.

One node per backend (no standard/advanced split — the only difference was a
couple of sliders nobody wanted two nodes for):

  SkillPromptOptimizer            OpenAI-compatible HTTP endpoint
  SkillPromptOptimizerLlamaCpp    in-process llama.cpp (GGUF)

Canvas contract
---------------
``width`` / ``height`` are BOTH an input and an output:

* input > 0  -> the canvas is fixed. The size is handed to the model as a hard
  composition constraint (and, for Layout, as the bbox bounds). The outputs echo
  the input; whatever size the model claims is ignored (mismatches are logged).
* input == 0 -> auto. The model picks the canvas itself and the size is parsed
  back out of the ``CANVAS: WxH`` line. This is the original behaviour.
* both must be 0 or both > 0.

There is deliberately no "custom_skill" input: a skill is always a folder with a
SKILL.md, so the rulebook a workflow used stays visible, versionable and reusable.
Per-run tweaks belong in ``extra_instruction``, which appends and never overrides.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from . import http_client, llamacpp_client
from .promptkit import sanitize_output
from .skills import estimate_tokens, get_skill, skill_choices

CATEGORY = "SkillPrompt"
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"

LANGUAGE_HINTS = {
    "English": "语言：英文（默认）。只输出英文正向提示词。",
    "中文": "语言：中文。只输出中文正向提示词。",
    "Bilingual": "语言：双语。输出两份各自完整、语义一致的独立版本（英文版 + 中文版），分别标注 English: 与中文:。",
}

FORMAT_HINTS = {
    "auto": "格式：按 skill 的规则自动判断（Caption / Tag / Layout）。",
    "caption": "格式：Caption。输出连贯的纯文本正向提示词，不要 JSON。",
    "tag": "格式：Tag。输出逗号分隔的标签串，画风句放在最前面。",
    "layout": "格式：Layout。",
}

SKILL_TOOLTIP = "写词规则书：skills/<名称>/SKILL.md 全文作为 system 提示词。新增技能后重启 ComfyUI。"
PROMPT_TOOLTIP = "原始需求：tag 串、一句话或一段中文描述都行。"
EXTRA_TOOLTIP = "本次追加要求（如“不要画标题”）。只追加，不覆盖 skill 规则。"
LANG_TOOLTIP = "English 默认；中文只出中文；Bilingual 出两份各自完整的版本。"
FORMAT_TOOLTIP = "auto 交给 skill 判断；caption / tag / layout 强制格式。"
TEMP_TOOLTIP = "遵循规则建议 0.5 左右。"
TOPP_TOOLTIP = "核采样阈值，一般 0.9。"
MAXTOK_TOOLTIP = "思考型模型会先花大量 token 在隐藏推理上，2048 起步更稳。"
TIMEOUT_TOOLTIP = "单次请求超时（秒）。本地 27B + 完整模板首次 prefill 可能要一两分钟。"
BASEURL_TOOLTIP = "OpenAI 兼容端点，如 http://127.0.0.1:11434/v1（Ollama）、http://127.0.0.1:8491/v1（llama.cpp router）。"
GGUF_TOOLTIP = "ComfyUI/models/LLM/ 下的 .gguf。缺模型可设环境变量 SKILLPROMPT_GGUF_DIRS。"
CTX_TOOLTIP = "上下文窗口。完整版 skill 约 21k tokens，建议 32768 起步。"
LAYERS_TOOLTIP = "-1 表示全部层放 GPU；显存不够时调小。"
KEEP_TOOLTIP = "True 保留模型在显存里加速下一次；显存紧张时关掉。"
WIDTH_TOOLTIP = "画布宽。＞0 时作为硬约束交给模型，并原样输出；0 = 让模型自己决定（从 CANVAS 行解析）。Layout 模式要求 16 的倍数。"
HEIGHT_TOOLTIP = "画布高。＞0 时作为硬约束交给模型，并原样输出；0 = 让模型自己决定。Layout 模式要求 16 的倍数。"

Sender = Callable[[List[Dict[str, str]], int], Tuple[str, Any]]


def _canvas_hint(width: int, height: int) -> str:
    return (
        f"画布尺寸：{width}×{height}（宽×高，已固定，不要改动）。"
        "景别、主体占比、留白与引导线都要按这个比例安排。"
    )


def _layout_contract(width: int, height: int) -> str:
    if width > 0 and height > 0:
        size_rule = (
            f"5. 画布固定为 {width}x{height}：每个 bbox 必须满足 "
            f"0<=x0<x1<={width} 且 0<=y0<y1<={height}，不要输出其他尺寸。\n"
            f"6. JSON 之后另起一行写 CANVAS: {width}x{height}。"
        )
    else:
        size_rule = "5. JSON 之后另起一行写 CANVAS: WxH（例如 CANVAS: 1024x1024）。"
    return (
        "Layout 流水线要求（优先于 skill 中关于最终坐标换算的说明）：\n"
        "1. 输出「草稿」JSON，根字段为 width、height、bbox_coord_space=\"abs\"、bbox_format=\"xyxy\"、summary、items。\n"
        "2. items 是扁平数组；每个单元含 label（character/object/text）、caption、bbox；text 项另含 text。\n"
        "3. bbox 用全图左上角像素坐标 [x0,y0,x1,y1]。\n"
        "4. 不要自行换算中心化坐标，也不要输出 yxyx — 由后处理节点做确定性编译。\n"
        + size_rule
    )


def _build_messages(
    prompt: str,
    skill_text: str,
    language: str,
    output_format: str,
    extra_instruction: str,
    width: int = 0,
    height: int = 0,
) -> List[Dict[str, str]]:
    fixed = width > 0 and height > 0
    parts = ["[用户画面需求]", (prompt or "").strip(), "", "[本次输出要求]"]
    if fixed:
        parts.append(_canvas_hint(width, height))
    parts.append(LANGUAGE_HINTS.get(language, LANGUAGE_HINTS["English"]))
    parts.append(FORMAT_HINTS.get(output_format, FORMAT_HINTS["auto"]))
    if output_format == "layout":
        parts += ["", _layout_contract(width, height)]
    extra = (extra_instruction or "").strip()
    if extra:
        parts += ["", "[附加要求]", extra]
    if output_format == "layout":
        parts += ["", "只输出草稿 JSON 与 CANVAS 行，不复述规则、不加解释。"]
    else:
        parts += ["", "只输出最终正向提示词正文；不复述规则、不加解释、不附加质量词或画师名。"]
    return [
        {"role": "system", "content": skill_text},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _check_canvas(width: int, height: int, output_format: str) -> None:
    w, h = int(width), int(height)
    if (w > 0) != (h > 0):
        raise ValueError(
            "width 与 height 要么都填 0（自动判断画布），要么都填 ≥16 的尺寸；只填一边无法确定构图比例。"
        )
    if w <= 0:
        return
    if output_format == "layout" and (w % 16 or h % 16):
        raise ValueError(
            f"Layout 模式要求画布宽高是 16 的倍数，收到 {w}x{h}。"
            "改用 1024x1024 / 1536x1024 / 1024x1536 / 768x1344 之类。"
        )
    if w < 16 or h < 16:
        raise ValueError(f"画布太小：{w}x{h}，宽高都需 ≥16。")


def _generate(
    prompt: str,
    skill: str,
    extra_instruction: str,
    language: str,
    output_format: str,
    width: int,
    height: int,
    sender: Sender,
) -> Tuple[str, str, int, int]:
    """Shared pipeline: resolve skill -> build messages -> call backend -> sanitise."""
    _check_canvas(width, height, output_format)
    fixed = int(width) > 0 and int(height) > 0

    info = get_skill(skill)
    skill_text = info["text"]
    est = estimate_tokens(skill_text) + estimate_tokens(prompt or "")
    canvas_note = f"{width}x{height} (fixed)" if fixed else "auto"
    print(
        f"[SkillPrompt] skill={info['name']} (~{info['tokens']} tok) "
        f"est_tokens≈{est} format={output_format} lang={language} canvas={canvas_note}"
    )

    messages = _build_messages(
        prompt, skill_text, language, output_format, extra_instruction, int(width), int(height)
    )
    text, usage = sender(messages, est)

    if usage:
        print(f"[SkillPrompt] usage={usage}")
        if usage.get("finish_reason") == "length":
            print(
                "[SkillPrompt] 警告：输出被 max_tokens 截断（finish_reason=length）。"
                "思考型模型会先消耗大量 token 在隐藏推理上，把 max_tokens 调大再试。"
            )

    clean = sanitize_output(text)
    for note in clean["notes"]:
        print(f"[SkillPrompt] {note}")

    if fixed:
        out_w, out_h = int(width), int(height)
        if clean["width"] and (clean["width"], clean["height"]) != (out_w, out_h):
            print(
                f"[SkillPrompt] 模型回报的画布 {clean['width']}x{clean['height']} "
                f"与固定输入 {out_w}x{out_h} 不一致，以输入为准。"
            )
    else:
        out_w, out_h = int(clean["width"]), int(clean["height"])

    size_note = f"{out_w}x{out_h}" if out_w and out_h else ""
    return clean["prompt"], size_note, out_w, out_h


def _http_sender(base_url: str, api_key: str, model: str, temperature: float,
                 top_p: float, max_tokens: int, timeout: int) -> Sender:
    def sender(messages: List[Dict[str, str]], est: int):
        if est > 24000:
            print(f"[SkillPrompt] 警告：系统提示约 {est} tokens，确认服务端上下文窗口够大（≥32k 更稳妥）。")
        return http_client.chat_completion(
            base_url=base_url, api_key=api_key, model=model, messages=messages,
            temperature=temperature, top_p=top_p, max_tokens=max_tokens, timeout=timeout,
        )

    return sender


def _llamacpp_sender(gguf_model: str, n_ctx: int, n_gpu_layers: int, chat_format: str,
                     keep_model_loaded: bool, seed: int, temperature: float,
                     top_p: float, max_tokens: int) -> Sender:
    def sender(messages: List[Dict[str, str]], est: int):
        need = est + int(max_tokens) + 256
        if int(n_ctx) < need:
            raise ValueError(
                f"上下文不够：skill + 提示词约 {est} tokens，加 max_tokens={max_tokens} 需要 ≥ {need}，"
                f"当前 n_ctx={n_ctx}。把 n_ctx 调大（注意显存），或改用精简版 skill。"
            )
        return llamacpp_client.chat_completion(
            model_name=gguf_model, messages=messages, n_ctx=int(n_ctx),
            n_gpu_layers=int(n_gpu_layers), chat_format=chat_format or "",
            temperature=float(temperature), top_p=float(top_p), max_tokens=int(max_tokens),
            seed=int(seed), keep_model_loaded=bool(keep_model_loaded),
        )

    return sender


# --------------------------------------------------------------------------- #
# HTTP backend
# --------------------------------------------------------------------------- #
class SkillPromptOptimizer:
    """Any OpenAI-compatible endpoint (Ollama / LM Studio / llama.cpp / cloud)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": PROMPT_TOOLTIP}),
                "skill": (skill_choices(), {"tooltip": SKILL_TOOLTIP}),
                "width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 16, "tooltip": WIDTH_TOOLTIP}),
                "height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 16, "tooltip": HEIGHT_TOOLTIP}),
                "base_url": ("STRING", {"default": DEFAULT_BASE_URL, "tooltip": BASEURL_TOOLTIP}),
                "model": ("STRING", {"default": "", "tooltip": "服务端实际暴露的模型名。"}),
                "api_key": ("STRING", {"default": "", "tooltip": "本地端点留空；云端服务填 key。"}),
                "language": (["English", "中文", "Bilingual"], {"tooltip": LANG_TOOLTIP}),
                "output_format": (["auto", "caption", "tag", "layout"], {"tooltip": FORMAT_TOOLTIP}),
                "temperature": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 2.0, "step": 0.05, "tooltip": TEMP_TOOLTIP}),
                "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": TOPP_TOOLTIP}),
                "max_tokens": ("INT", {"default": 2048, "min": 64, "max": 32768, "step": 64, "tooltip": MAXTOK_TOOLTIP}),
                "timeout": ("INT", {"default": 600, "min": 30, "max": 3600, "step": 30, "tooltip": TIMEOUT_TOOLTIP}),
                "extra_instruction": ("STRING", {"multiline": True, "default": "", "tooltip": EXTRA_TOOLTIP}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("optimized_prompt", "size_note", "width", "height")
    FUNCTION = "optimize"
    CATEGORY = CATEGORY

    def optimize(self, prompt, skill, width, height, base_url, model, api_key,
                 language, output_format, temperature, top_p, max_tokens, timeout,
                 extra_instruction):
        sender = _http_sender(base_url, api_key, model, temperature, top_p, max_tokens, timeout)
        return _generate(prompt, skill, extra_instruction, language, output_format,
                         width, height, sender)


# --------------------------------------------------------------------------- #
# llama.cpp backend
# --------------------------------------------------------------------------- #
class SkillPromptOptimizerLlamaCpp:
    """In-process llama.cpp backend (requires llama-cpp-python)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": PROMPT_TOOLTIP}),
                "skill": (skill_choices(), {"tooltip": SKILL_TOOLTIP}),
                "width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 16, "tooltip": WIDTH_TOOLTIP}),
                "height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 16, "tooltip": HEIGHT_TOOLTIP}),
                "gguf_model": (llamacpp_client.list_gguf_models(), {"tooltip": GGUF_TOOLTIP}),
                "n_ctx": ("INT", {"default": 32768, "min": 2048, "max": 262144, "step": 1024, "tooltip": CTX_TOOLTIP}),
                "n_gpu_layers": ("INT", {"default": -1, "min": -1, "max": 999, "step": 1, "tooltip": LAYERS_TOOLTIP}),
                "chat_format": ("STRING", {"default": "", "tooltip": "留空用模型自带模板；个别 GGUF 需手动指定，如 chatml。"}),
                "keep_model_loaded": ("BOOLEAN", {"default": True, "tooltip": KEEP_TOOLTIP}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2 ** 63 - 1, "step": 1, "tooltip": "-1 不固定；固定 seed 便于复现。"}),
                "temperature": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 2.0, "step": 0.05, "tooltip": TEMP_TOOLTIP}),
                "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": TOPP_TOOLTIP}),
                "max_tokens": ("INT", {"default": 2048, "min": 64, "max": 32768, "step": 64, "tooltip": MAXTOK_TOOLTIP}),
                "language": (["English", "中文", "Bilingual"], {"tooltip": LANG_TOOLTIP}),
                "output_format": (["auto", "caption", "tag", "layout"], {"tooltip": FORMAT_TOOLTIP}),
                "extra_instruction": ("STRING", {"multiline": True, "default": "", "tooltip": EXTRA_TOOLTIP}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("optimized_prompt", "size_note", "width", "height")
    FUNCTION = "optimize"
    CATEGORY = CATEGORY

    def optimize(self, prompt, skill, width, height, gguf_model, n_ctx, n_gpu_layers,
                 chat_format, keep_model_loaded, seed, temperature, top_p, max_tokens,
                 language, output_format, extra_instruction):
        sender = _llamacpp_sender(gguf_model, n_ctx, n_gpu_layers, chat_format,
                                  keep_model_loaded, seed, temperature, top_p, max_tokens)
        return _generate(prompt, skill, extra_instruction, language, output_format,
                         width, height, sender)
