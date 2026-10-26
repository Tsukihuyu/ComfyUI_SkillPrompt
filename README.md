# SkillPrompt for ComfyUI

**Write prompts with rules, not vibes.**

SkillPrompt turns a rough idea — a tag soup, a one-line brief, a Chinese sentence —
into a structured positive prompt by running it through **an LLM + a markdown skill**.
A *skill* is a complete prompt-writing rulebook (rules, formats, examples, several
thousand tokens long). The bundled skill is the MOSS anime prompt template; you can
drop your own rulebook in without touching code.

Two things make this different from a generic "prompt enhancer":

1. **Template fidelity** — the skill text is the LLM's system prompt, verbatim. Full
   rulebooks (21k tokens) are supported, with a slim variant for small contexts.
2. **A deterministic Layout compiler** — the LLM only *designs* the layout; all
   coordinate arithmetic is done in Python, where it can be checked and tested.

---

## Nodes

| Node | What it does |
|---|---|
| **Skill Prompt Optimizer** | OpenAI-compatible HTTP endpoint (Ollama / LM Studio / llama.cpp server / cloud). |
| **Skill Prompt Optimizer (llama.cpp)** | In-process GGUF backend: `gguf_model`, `n_ctx`, `n_gpu_layers`, `chat_format`, `seed`. |
| **Skill Prompt Layout Compiler** | Takes the LLM's Layout *draft* (`bbox_coord_space="abs"`, `bbox_format="xyxy"`) and emits the final one-line JSON (`abs_centralized` / `yxyx`, integers), with structural validation. |

One node per backend: a node only shows the widgets it uses, and there is no `backend`
switch or hidden override anywhere.

---

## Install

```bash
cd ComfyUI/custom_nodes
git clone <this repo>
# restart ComfyUI
```

No pip dependencies for the HTTP backend (`urllib` only, Python ≥ 3.10).

Optional, for the in-process llama.cpp backend:

```bash
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

(Wheel suffix must match your CUDA runtime. Without `llama-cpp-python` the node still
works — the `llama_cpp` backend just reports an install hint.)

---

## Quick start

1. Add **Skill Prompt Optimizer**.
2. Pick a `skill` — `moss-anime-prompt-slim` for small contexts, `moss-anime-prompt`
   for the full rulebook.
3. Fill `base_url` + `model`:

| Backend | base_url | Notes |
|---|---|---|
| Ollama | `http://127.0.0.1:11434/v1` | model e.g. `qwen2.5:14b-instruct` |
| LM Studio | `http://127.0.0.1:1234/v1` | model = the id shown in the server tab |
| llama.cpp server | `http://127.0.0.1:8080/v1` | model = the loaded model's path |
| DeepSeek | `https://api.deepseek.com/v1` | api_key required, model = `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | api_key required |

4. Paste your rough prompt, pick `output_format` (`auto` / `caption` / `tag` / `layout`),
   run. Wire `optimized_prompt` into a `CLIPTextEncode`.

Local endpoints need no api_key.

---

## Skills

```
skills/
  moss-anime-prompt/SKILL.md        # full template  (~21k tokens, needs ≥32k context)
  moss-anime-prompt-slim/SKILL.md   # §17 extract   (~4k tokens, fits 16k context)
  your-skill/SKILL.md               # your own rulebook
```

- Each skill is a folder containing `SKILL.md`; the file text becomes the system message.
- Optional `meta.json`: `{"display_name": "...", "language": "zh+en", "notes": "..."}`.
- Extra skill folders: set `SKILLPROMPT_SKILL_DIRS` (path-separator separated).
- Adding a skill requires a ComfyUI restart (the dropdown is built at load time).
- Need to bend the rules for one run? Use `extra_instruction` (appends). To change the
  rules themselves, make a skill folder — that keeps the exact rulebook in the workflow
  history instead of hiding it in a text box.

> **Security note:** skills are *text guidance only* — the node never executes anything
> from them. But they are injected as the system prompt, so an untrusted skill can steer
> the model (prompt injection). Treat third-party skills like third-party code.

---

## Layout pipeline

Template-authoring skills like MOSS use a **draft → final** split. LLMs are unreliable at
arithmetic; the compiler is not.

1. Optionally set `width` / `height` first. `>0` fixes the canvas: the size goes into the
   user message as a composition constraint and, in Layout mode, as the hard bbox bounds
   (`0<=x1<=W`). The outputs then echo those numbers. `0` = let the model choose.
2. Set `output_format = layout`. The optimizer appends a pipeline contract to the user
   message: emit a draft JSON (`width`, `height`, `bbox_coord_space="abs"`,
   `bbox_format="xyxy"`, `summary`, `items`) followed by a `CANVAS: WxH` line.
3. The node strips the `CANVAS:` line out of the prompt body and exposes the size as
   `size_note` / `width` / `height` outputs.
4. Feed the prompt text into **Skill Prompt Layout Compiler** (or trust the draft as-is
   if your model consumes drafts directly). The compiler:
   - converts `[x0,y0,x1,y1]` → `[y0-H/2, x0-W/2, y1-H/2, x1-W/2]`,
   - floors left/top and ceils right/bottom on fractional edges,
   - drops non-schema root fields, validates `label` enums, `text` items, box area,
     bounds, and the 16-pixel-multiple canvas rule,
   - returns a single-line JSON string plus a human-readable `status`.

Example output (1024×1024, one item at `[100,320,440,760]`):

```json
{"summary":{...},"items":[{"label":"object","caption":"...","bbox":[-192,-412,248,-72]}],"bbox_coord_space":"abs_centralized","bbox_format":"yxyx"}
```

---

## Parameter notes

| Parameter | Meaning |
|---|---|
| `width` / `height` | **In and out.** `>0` = fixed canvas: the size is passed to the model as a hard composition constraint (and the bbox bounds in Layout mode), and echoed back on the outputs. `0` = auto: the model picks the canvas and the size is parsed from its `CANVAS:` line. Fill both or neither. Layout mode requires multiples of 16. |
| `language` | `English` (default), `中文`, `Bilingual` (two complete versions) |
| `output_format` | `auto` lets the skill decide; `caption` / `tag` / `layout` force a format |
| `temperature` | 0.5 is a good starting point for rule-following |
| `top_p` | 0.9 is a sane default; rarely worth touching |
| `max_tokens` | **Headroom matters**: thinking models spend most tokens on hidden reasoning. If the text looks cut off, check the console for the `finish_reason=length` warning and raise this. |
| `n_ctx` | llama.cpp only. The node refuses to run when skill + prompt + `max_tokens` exceed it, and tells you the numbers. |
| `keep_model_loaded` | llama.cpp only. `false` unloads and frees VRAM after every run. |

---

## Limits, honestly

- **Context**: the full MOSS rulebook is ~21k tokens. Use the slim skill below ~32k context.
- **Model quality**: rule-following degrades fast under ~14B. A 27B-class model is a
  reasonable floor for the full rulebook.
- **Latency**: the first call pays prefill for the whole rulebook; later calls reuse the
  server's prompt cache when it has one (llama.cpp servers do; observed `cached_tokens`
  in usage).
- **LLM arithmetic**: never trust an LLM to convert coordinates. That is what the
  compiler is for.
- **Not a local image editor**: the compiler re-derives coordinates; it does not edit
  pixels.

---

## Credits

- Bundled skill text: **MOSS 二次元提示词模板（sfw版）** by 是古手梨花sama (Bilibili),
  included verbatim with attribution.
- Architecture inspiration: [ComfyUI_Qwen_H3_Prompt](https://github.com/chflame163/ComfyUI_Qwen_H3_Prompt)
  (MIT) and [ComfyUI-QwenVL](https://github.com/1038lab/ComfyUI-QwenVL) (GPL-3.0).
  This project is an independent implementation — no code copied from either.

## License

MIT (see `LICENSE`). The bundled MOSS template text remains the property of its author.
