"""SkillPrompt optimizer nodes (Standard + Advanced)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from . import http_client, llamacpp_client
from .promptkit import sanitize_output
from .skills import PLACEHOLDER, estimate_tokens, get_skill, skill_choices

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

LAYOUT_CONTRACT = """Layout 流水线要求（优先于 skill 中关于最终坐标换算的说明）：
1. 输出「草稿」JSON，根字段为 width、height、bbox_coord_space="abs"、bbox_format="xyxy"、summary、items。
2. items 是扁平数组；每个单元含 label（character/object/text）、caption、bbox；text 项另含 text。
3. bbox 用全图左上角像素坐标 [x0,y0,x1,y1]；画布宽高必须是 16 的倍数。
4. 不要自行换算中心化坐标，也不要输出 yxyx — 由后处理节点做确定性编译。
5. JSON 之后另起一行写 CANVAS: WxH（例如 CANVAS: 1024x1024）。"""


def _build_messages(
    prompt: str,
    skill_text: str,
    language: str,
    output_format: str,
    extra_instruction: str,
) -> List[Dict[str, str]]:
    parts = ["[用户画面需求]", (prompt or "").strip(), "", "[本次输出要求]"]
    parts.append(LANGUAGE_HINTS.get(language, LANGUAGE_HINTS["English"]))
    parts.append(FORMAT_HINTS.get(output_format, FORMAT_HINTS["auto"]))
    if output_format == "layout":
        parts += ["", LAYOUT_CONTRACT]
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


def _run(
    prompt: str,
    skill: str,
    custom_skill: str,
    backend: str,
    base_url: str,
    api_key: str,
    model: str,
    gguf_model: str,
    n_ctx: int,
    n_gpu_layers: int,
    chat_format: str,
    keep_model_loaded: bool,
    seed: int,
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout: int,
    language: str,
    output_format: str,
    extra_instruction: str,
) -> Tuple[str, str, int, int]:
    custom = (custom_skill or "").strip()
    if custom:
        skill_text = custom
        skill_label = "custom_skill"
    else:
        info = get_skill(skill)
        skill_text = info["text"]
        skill_label = f"{info['name']} (~{info['tokens']} tok)"

    est = estimate_tokens(skill_text) + estimate_tokens(prompt or "")
    print(
        f"[SkillPrompt] skill={skill_label} est_tokens≈{est} "
        f"backend={backend} format={output_format} lang={language}"
    )

    messages = _build_messages(prompt, skill_text, language, output_format, extra_instruction)

    if backend == "llama_cpp":
        need = est + int(max_tokens) + 256
        if int(n_ctx) < need:
            raise ValueError(
                f"上下文不够：skill + 提示词约 {est} tokens，加 max_tokens={max_tokens} 需要 ≥ {need}，"
                f"当前 n_ctx={n_ctx}。把 n_ctx 调大（注意显存），或改用精简版 skill。"
            )
        text, _usage = llamacpp_client.chat_completion(
            model_name=gguf_model,
            messages=messages,
            n_ctx=int(n_ctx),
            n_gpu_layers=int(n_gpu_layers),
            chat_format=chat_format or "",
            temperature=float(temperature),
            top_p=float(top_p),
            max_tokens=int(max_tokens),
            seed=int(seed),
            keep_model_loaded=bool(keep_model_loaded),
        )
    else:
        if est > 24000:
            print(
                f"[SkillPrompt] 警告：系统提示约 {est} tokens，"
                "确认服务端模型的上下文窗口够大（≥32k 更稳妥）。"
            )
        text, _usage = http_client.chat_completion(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=float(temperature),
            top_p=float(top_p),
            max_tokens=int(max_tokens),
            timeout=int(timeout),
        )
    if _usage:
        print(f"[SkillPrompt] usage={_usage}")
        if _usage.get("finish_reason") == "length":
            print(
                "[SkillPrompt] 警告：输出被 max_tokens 截断（finish_reason=length）。"
                "思考型模型会先消耗大量 token 在隐藏推理上，把 max_tokens 调大再试。"
            )

    clean = sanitize_output(text)
    for note in clean["notes"]:
        print(f"[SkillPrompt] {note}")
    width, height = int(clean["width"]), int(clean["height"])
    size_note = f"{width}x{height}" if width and height else ""
    return clean["prompt"], size_note, width, height


class SkillPromptOptimizer:
    """Standard node: OpenAI-compatible endpoint, three core inputs."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "skill": (skill_choices(),),
                "custom_skill": ("STRING", {"multiline": True, "default": ""}),
                "base_url": ("STRING", {"default": DEFAULT_BASE_URL}),
                "model": ("STRING", {"default": ""}),
                "api_key": ("STRING", {"default": ""}),
                "language": (["English", "中文", "Bilingual"],),
                "output_format": (["auto", "caption", "tag", "layout"],),
                "temperature": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 2.0, "step": 0.05}),
                "max_tokens": ("INT", {"default": 2048, "min": 64, "max": 32768, "step": 64}),
                "timeout": ("INT", {"default": 600, "min": 30, "max": 3600, "step": 30}),
                "extra_instruction": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("optimized_prompt", "size_note", "width", "height")
    FUNCTION = "optimize"
    CATEGORY = CATEGORY

    def optimize(
        self,
        prompt: str,
        skill: str,
        custom_skill: str,
        base_url: str,
        model: str,
        api_key: str,
        language: str,
        output_format: str,
        temperature: float,
        max_tokens: int,
        timeout: int,
        extra_instruction: str,
    ):
        return _run(
            prompt=prompt,
            skill=skill,
            custom_skill=custom_skill,
            backend="http",
            base_url=base_url,
            api_key=api_key,
            model=model,
            gguf_model=PLACEHOLDER,
            n_ctx=32768,
            n_gpu_layers=-1,
            chat_format="",
            keep_model_loaded=True,
            seed=-1,
            temperature=temperature,
            top_p=0.9,
            max_tokens=max_tokens,
            timeout=timeout,
            language=language,
            output_format=output_format,
            extra_instruction=extra_instruction,
        )


class SkillPromptOptimizerAdvanced:
    """Advanced node: HTTP or in-process llama.cpp, full parameter control."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "skill": (skill_choices(),),
                "custom_skill": ("STRING", {"multiline": True, "default": ""}),
                "backend": (["http", "llama_cpp"],),
                "base_url": ("STRING", {"default": DEFAULT_BASE_URL}),
                "model": ("STRING", {"default": ""}),
                "api_key": ("STRING", {"default": ""}),
                "gguf_model": (llamacpp_client.list_gguf_models(),),
                "n_ctx": ("INT", {"default": 32768, "min": 2048, "max": 262144, "step": 1024}),
                "n_gpu_layers": ("INT", {"default": -1, "min": -1, "max": 999, "step": 1}),
                "chat_format": ("STRING", {"default": ""}),
                "keep_model_loaded": ("BOOLEAN", {"default": True}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2 ** 63 - 1, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.05}),
                "max_tokens": ("INT", {"default": 2048, "min": 64, "max": 32768, "step": 64}),
                "timeout": ("INT", {"default": 600, "min": 30, "max": 3600, "step": 30}),
                "language": (["English", "中文", "Bilingual"],),
                "output_format": (["auto", "caption", "tag", "layout"],),
                "extra_instruction": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("optimized_prompt", "size_note", "width", "height")
    FUNCTION = "optimize"
    CATEGORY = CATEGORY

    def optimize(
        self,
        prompt: str,
        skill: str,
        custom_skill: str,
        backend: str,
        base_url: str,
        model: str,
        api_key: str,
        gguf_model: str,
        n_ctx: int,
        n_gpu_layers: int,
        chat_format: str,
        keep_model_loaded: bool,
        seed: int,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout: int,
        language: str,
        output_format: str,
        extra_instruction: str,
    ):
        return _run(
            prompt=prompt,
            skill=skill,
            custom_skill=custom_skill,
            backend=backend,
            base_url=base_url,
            api_key=api_key,
            model=model,
            gguf_model=gguf_model,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            chat_format=chat_format,
            keep_model_loaded=keep_model_loaded,
            seed=seed,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout=timeout,
            language=language,
            output_format=output_format,
            extra_instruction=extra_instruction,
        )
