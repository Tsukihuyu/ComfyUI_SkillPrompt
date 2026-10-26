# SkillPrompt for ComfyUI

**Write prompts from a rulebook, not from vibes.**

Give the node a rough idea — a tag soup, a one-line brief, a Chinese sentence — and it
runs it through an **LLM + a markdown skill** (a complete prompt-writing rulebook in a
`SKILL.md`) and hands back a structured positive prompt, ready for `CLIPTextEncode`.

Two things separate it from a generic "prompt enhancer":

1. **Skill fidelity** — the skill text *is* the system prompt, verbatim. A 20k-token
   rulebook works as well as a 10-line one, and per-run tweaks go in a separate
   `extra_instruction` field that appends instead of silently overriding.
2. **A deterministic Layout compiler** — the LLM only *designs* a layout; every
   coordinate conversion happens in Python, where it is validated and unit-tested.

---

## Nodes

| Node | What it does |
|---|---|
| **Skill Prompt Optimizer** | Runs your prompt through a configured endpoint + skill. Returns the prompt, and the canvas size it resolved (or was given). |
| **Skill Prompt Layout Compiler** | Turns a Layout *draft* (`bbox_coord_space="abs"`, `bbox_format="xyxy"`) into the final one-line JSON (`abs_centralized` / `yxyx`, integers), with structural validation. |

No in-process model loading, no bundled runtime: the node is a thin, dependency-free
client for whatever OpenAI-compatible server you already run.

---

## Install

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/<you>/ComfyUI_SkillPrompt.git
cp ComfyUI_SkillPrompt/skillprompt.ini.example ComfyUI_SkillPrompt/skillprompt.ini
# edit skillprompt.ini, then restart ComfyUI
```

Python ≥ 3.10, **zero pip dependencies** (`urllib` only). Tested on ComfyUI 0.42.x.

---

## Endpoints: `skillprompt.ini`

The node never shows a URL or an API key — they live in `skillprompt.ini`, one
`[section]` per dropdown entry:

```ini
[local-llamacpp]                     ; section name = stable id
name = local llama.cpp 27B           ; display name shown in the dropdown
base_url = http://127.0.0.1:8491/v1  ; OpenAI-compatible, up to /v1
model = YOUR-MODEL-NAME

[deepseek]
name = DeepSeek
base_url = https://api.deepseek.com/v1
model = deepseek-chat
api_key_env = DEEPSEEK_API_KEY       ; key from an env var, not from the file
```

- Works with llama.cpp (router or plain server), LM Studio, Ollama, vLLM, DeepSeek,
  OpenAI — anything that speaks `/v1/chat/completions`.
- Sections named `example*` are ignored; sections missing `base_url` or `model` are skipped.
- `api_key` is used when present; `api_key_env` takes precedence and keeps the key off disk.
- `SKILLPROMPT_CONFIG=<path>` points the node at a different ini.
- **Restart ComfyUI after editing** (the dropdown is built at load time).
- `skillprompt.ini` is git-ignored. Keep it that way.

---

## Skills

A skill is a folder under `skills/` containing a `SKILL.md`; its full text becomes the
system message. See [`skills/README.md`](skills/README.md) for the format and a minimal
skeleton.

**This repository ships no prompt text** — the well-known anime prompt templates are
third-party works by their own authors. Bring your own rulebook.

- Extra folders: `SKILLPROMPT_SKILL_DIRS` (path-separator separated).
- Restart ComfyUI after adding a skill.
- A skill is text guidance only — the node executes nothing from it. But it *is* the
  system prompt, so treat third-party skills like third-party code.

---

## Canvas: `width` / `height` are in **and** out

| Value | Behaviour |
|---|---|
| `> 0` | Fixed canvas. Handed to the model as a hard composition constraint (and, in Layout mode, as the bbox bounds), then echoed on the outputs. |
| `0` | Auto. The model picks the canvas and the size is parsed back from its `CANVAS: WxH` line. |

Fill both or neither. Layout mode requires multiples of 16 (the template arithmetic needs
integer centres). Wire the outputs into `EmptyLatentImage` and the compiler so the whole
graph agrees on one size.

---

## Layout pipeline

1. Set `output_format = layout`. The node appends a pipeline contract: emit a **draft**
   JSON (`width`, `height`, `bbox_coord_space="abs"`, `bbox_format="xyxy"`, `summary`,
   `items`) plus a `CANVAS: WxH` line.
2. The node strips that line out of the prompt body and exposes the size as outputs.
3. Feed the text into **Skill Prompt Layout Compiler**. It converts
   `[x0,y0,x1,y1]` → `[y0-H/2, x0-W/2, y1-H/2, x1-W/2]`, floors/ceils fractional edges,
   drops non-schema fields, validates `label` enums, `text` items, box area, canvas bounds
   and the 16-multiple rule, and returns one line of compact JSON plus a readable status.

LLMs are unreliable at arithmetic; this step is not. The compiler has ~20 unit tests of
its own.

---

## Other switches

| Parameter | Meaning |
|---|---|
| `disable_thinking` | **On by default.** Sends `chat_template_kwargs={"enable_thinking": false}` (llama.cpp server / LM Studio / vLLM / SGLang); if a server rejects the field it retries once with a `/no_think` prompt suffix. Turn it off only if you want the reasoning pass. |
| `unload_after_run` | **On by default.** Asks the server to drop the model after the prompt is written, so the image model gets the VRAM: `POST {root}/models/unload` (llama.cpp router), `POST {root}/api/v1/models/unload` (LM Studio), `POST {root}/api/generate` with `keep_alive: 0` (Ollama). Cloud endpoints just report "no unload endpoint". Turn it off when writing many prompts in a row. |
| `temperature` / `top_p` | 0.5 / 0.9 is a good starting point for rule-following. |
| `max_tokens` | **Headroom matters.** Thinking models burn most of it on hidden reasoning; the console warns when the reply hits `finish_reason=length`. |
| `language` | `English` (default), `中文`, `Bilingual` (two complete versions). |
| `output_format` | `auto` lets the skill decide; `caption` / `tag` / `layout` force a format. |

---

## Limits, honestly

- **Model size matters.** Rule-following degrades fast below ~14B; a 20k-token rulebook is
  best served by a 27B-class model.
- **Latency.** The first call pays prefill for the whole rulebook; later calls are faster
  when the server keeps a prompt cache (`cached_tokens` shows up in `usage`).
- **Thinking models.** If an endpoint honours neither `chat_template_kwargs` nor
  `/no_think` and inlines untagged reasoning into `content`, the node cannot tell prose
  from prompt — fix it on the server side. Tagged `think` blocks are stripped.
- **Unload support varies.** Servers not in the list simply report that no unload endpoint
  exists; nothing breaks.
- **Not an image editor.** The compiler re-derives coordinates; it does not touch pixels.

---

## Credits & license

MIT (see `LICENSE`).

Design inspiration: [ComfyUI_Qwen_H3_Prompt](https://github.com/chflame163/ComfyUI_Qwen_H3_Prompt)
(MIT) and [ComfyUI-QwenVL](https://github.com/1038lab/ComfyUI-QwenVL) (GPL-3.0). This is an
independent implementation; no code was copied from either project.
