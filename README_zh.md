# SkillPrompt for ComfyUI

**写提示词靠规则书，不靠玄学。**

把一段粗糙的想法——一串 tag、一句需求、一段中文描述——交给节点，它经过 **LLM + markdown 技能**
（一份完整的写词规则书 `SKILL.md`）重写成结构化正向提示词，直接接 `CLIPTextEncode`。

和普通“提示词增强器”的两点不同：

1. **模板忠实度**：技能全文就是 system 提示词，原样使用。两万 token 的规则书和十行的规则书
   一样能跑；单次微调交给 `extra_instruction`，它是**追加**，不会静默覆盖技能。
2. **确定性 Layout 编译器**：LLM 只负责“设计版式”，所有坐标换算交给 Python，可校验、可测试。

---

## 两个节点

| 节点 | 作用 |
|---|---|
| **Skill Prompt Optimizer** | 用配置好的端点和技能重写提示词，输出提示词本身，以及本次解析出的画布尺寸。 |
| **Skill Prompt Layout Compiler** | 把 Layout **草稿**（`bbox_coord_space="abs"`、`bbox_format="xyxy"`）编译成最终单行 JSON（`abs_centralized` / `yxyx` 整数），并做结构校验。 |

不加载本地模型、不打包运行时：节点就是一个零依赖的客户端，连你自己已经在跑的服务。

---

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Tsukihuyu/ComfyUI_SkillPrompt.git
cp ComfyUI_SkillPrompt/skillprompt.ini.example ComfyUI_SkillPrompt/skillprompt.ini
# 编辑 skillprompt.ini，然后重启 ComfyUI
```

Python ≥ 3.10，**零 pip 依赖**（只用 `urllib`）。在 ComfyUI 0.42.x 上验证过。

---

## 端点：`skillprompt.ini`

节点界面上没有地址、没有 API key —— 它们都在 `skillprompt.ini` 里，一个 `[段]` 对应下拉框一项：

```ini
[local-llamacpp]                     ; 段名 = 稳定 id
name = 本地 llama.cpp 27B            ; 下拉框显示名
base_url = http://127.0.0.1:8491/v1  ; OpenAI 兼容端点，写到 /v1
model = YOUR-MODEL-NAME

[deepseek]
name = DeepSeek
base_url = https://api.deepseek.com/v1
model = deepseek-chat
api_key_env = DEEPSEEK_API_KEY       ; key 从环境变量读，不落盘
```

- 支持 llama.cpp（router 或普通 server）、LM Studio、Ollama、vLLM、DeepSeek、OpenAI，
  凡是会说 `/v1/chat/completions` 的都行。
- `example*` 开头的段会被忽略；缺 `base_url` 或 `model` 的段会被跳过。
- 有 `api_key` 就用它；`api_key_env` 优先级更高，可以把 key 完全留在系统环境里。
- `SKILLPROMPT_CONFIG=<路径>` 可以指向别的 ini。
- **改完要重启 ComfyUI**（下拉框在加载时构建）。
- `skillprompt.ini` 已进 `.gitignore`，请保持这样。

---

## 技能

`skills/` 下每个含 `SKILL.md` 的文件夹就是一个技能，文件全文作为 system 消息。
格式见 [`skills/README.md`](skills/README.md)，里面有一个最小骨架。

**本仓库不附带任何提示词文本**——流传的那几份二次元提示词模板是各自作者的作品，
版权归原作者。请自备规则书。

- 额外技能目录：环境变量 `SKILLPROMPT_SKILL_DIRS`（路径分隔符分隔）。
- 新增技能后重启 ComfyUI。
- 技能只是文本指导，节点不会执行其中任何东西；但它确实是 system 提示词，
  所以第三方技能要当第三方代码对待。

---

## 画布：`width` / `height` 既是输入也是输出

| 取值 | 行为 |
|---|---|
| `> 0` | 固定画布：作为硬性构图约束写给模型（Layout 模式下同时是 bbox 边界），并原样回显到输出。 |
| `0` | 自动：由模型决定，尺寸从它自己写的 `CANVAS: WxH` 行解析回来。 |

要么都填，要么都不填。Layout 模式要求 16 的倍数（模板的坐标换算需要整数中心）。
把输出接到 `EmptyLatentImage` 和编译器，整张图才对同一个尺寸有共识。

---

## Layout 流水线

1. 设 `output_format = layout`，节点会附加流水线契约：先输出**草稿** JSON
   （`width`、`height`、`bbox_coord_space="abs"`、`bbox_format="xyxy"`、`summary`、`items`），
   再另起一行 `CANVAS: WxH`。
2. 节点把这行摘掉，尺寸通过输出暴露出去。
3. 把提示词正文接进 **Skill Prompt Layout Compiler**。它把
   `[x0,y0,x1,y1]` 转成 `[y0-H/2, x0-W/2, y1-H/2, x1-W/2]`，小数边先取整，丢弃 schema 外字段，
   校验 `label` 枚举、`text` 项、框面积、画布越界与 16 倍数规则，
   输出一行紧凑 JSON 加一份可读状态。

LLM 的算术不可信，这一步可信——编译器自己就有二十来项单元测试。

---

## 其他开关

| 参数 | 含义 |
|---|---|
| `disable_thinking` | **默认开启。** 发送 `chat_template_kwargs={"enable_thinking": false}`（llama.cpp server / LM Studio / vLLM / SGLang 支持）；服务端不认该字段时自动退回 `/no_think` 后缀重试。只有确实想要推理过程时才关掉。 |
| `unload_after_run` | **默认开启。** 写完提示词就让服务端卸载模型，把显存让给出图模型：`POST {root}/models/unload`（llama.cpp router）、`POST {root}/api/v1/models/unload`（LM Studio）、`POST {root}/api/generate` 带 `keep_alive: 0`（Ollama）。云端端点只会回报“无此端点”。连续批量写词时关掉。 |
| `temperature` / `top_p` | 遵循规则的话 0.5 / 0.9 是好起点。 |
| `max_tokens` | **要留余量。** 思考型模型大半 token 花在隐藏推理上；撞到 `finish_reason=length` 时控制台会警告。 |
| `language` | `English`（默认）/ `中文` / `Bilingual`（两份各自完整的版本）。 |
| `output_format` | `auto` 由技能判断；`caption` / `tag` / `layout` 强制格式。 |

---

## 已知边界（不粉饰）

- **模型规模有下限。** 14B 以下遵循长规则的能力掉得很快；两万 token 的规则书建议 27B 级起步。
- **首次调用慢。** 第一次要为整份规则书付 prefill；服务端有前缀缓存时后续会快（`usage` 里的 `cached_tokens` 能看到）。
- **思考型模型**：如果某个端点既不认 `chat_template_kwargs` 也不认 `/no_think`，还把无标签的推理
  直接混进 `content`，节点分辨不出来——只能在服务端解决。带标签的 `think` 块会被自动剥掉。
- **卸载支持视服务端而定**：不在列表里的服务端只会回报一句“无此端点”，不影响结果。
- **不是局部重绘工具**：编译器重算坐标，不修改像素。

---

## 致谢与许可

MIT（见 `LICENSE`）。

设计参考：[ComfyUI_Qwen_H3_Prompt](https://github.com/chflame163/ComfyUI_Qwen_H3_Prompt)（MIT）、
[ComfyUI-QwenVL](https://github.com/1038lab/ComfyUI-QwenVL)（GPL-3.0）。本项目为独立实现，未复制其代码。
