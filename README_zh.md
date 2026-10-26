# SkillPrompt for ComfyUI

**写提示词靠规则，不靠玄学。**

把一段粗糙的想法——一串 tag、一句需求、一段中文描述——交给 **大语言模型 + markdown 技能**，
按技能里写好的规则重写成结构化的正向提示词。所谓“技能”就是一份完整的写词规则书
（规则、格式、示例，动辄几千到两万 tokens）。仓库自带 MOSS 二次元提示词模板，你也可以
把自己的规则书丢进去，不用改一行代码。

和普通“提示词增强器”的两点不同：

1. **模板忠实度**：技能全文原样作为 system 提示词，完整规则书（21k tokens）也支持，
   小上下文模型可用精简版。
2. **确定性 Layout 编译器**：LLM 只负责“设计版式”，所有坐标算术交给 Python 做——
   可校验、可测试、可复现。

---

## 三个节点

| 节点 | 作用 |
|---|---|
| **Skill Prompt Optimizer** | OpenAI 兼容 HTTP 端点（Ollama / LM Studio / llama.cpp server / 云端）。 |
| **Skill Prompt Layout Compiler** | 接收 Layout **草稿**（`abs` / `xyxy`），输出最终单行 JSON（`abs_centralized` / `yxyx` 整数），并做结构校验。 |

刻意不提供进程内 GGUF 后端：llama-cpp-python 无法关闭 Qwen3 系模型的思考（那个开关只存在于
`llama-server`），留着就是一条永远半残的路径。把 `base_url` 指向真正的服务端即可。

---

## 安装

```bash
cd ComfyUI/custom_nodes
git clone <本仓库>
# 重启 ComfyUI
```

零依赖（只用 `urllib`，Python ≥ 3.10）。

---

## 快速开始

1. 添加 **Skill Prompt Optimizer** 节点。
2. 选 `skill`：小上下文用 `moss-anime-prompt-slim`，32k 以上用 `moss-anime-prompt`。
3. 填 `base_url` 与 `model`：

| 后端 | base_url | 说明 |
|---|---|---|
| Ollama | `http://127.0.0.1:11434/v1` | 模型如 `qwen2.5:14b-instruct` |
| LM Studio | `http://127.0.0.1:1234/v1` | 模型名用服务页显示的 id |
| llama.cpp server | `http://127.0.0.1:8080/v1` | 模型名用已加载模型的路径 |
| DeepSeek | `https://api.deepseek.com/v1` | 需要 api_key，模型 `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | 需要 api_key |

4. 粘进粗糙提示词，选 `output_format`（`auto` / `caption` / `tag` / `layout`），运行。
   把 `optimized_prompt` 接到 `CLIPTextEncode`。

本地端点 api_key 留空即可。

---

## 技能目录

```
skills/
  moss-anime-prompt/SKILL.md        # 完整模板（约 21k tokens，需 ≥32k 上下文）
  moss-anime-prompt-slim/SKILL.md   # §17 提取（约 4k tokens，适配 16k 上下文）
  your-skill/SKILL.md               # 你自己的规则书
```

- 每个技能是一个含 `SKILL.md` 的目录，文件全文作为 system 消息。
- 可选 `meta.json`：`{"display_name": "...", "language": "zh+en", "notes": "..."}`。
- 额外技能目录：设环境变量 `SKILLPROMPT_SKILL_DIRS`（路径分隔符分隔）。
- 新增技能需要重启 ComfyUI（下拉框在加载时构建）。
- 只想临时加要求？用 `extra_instruction`（只追加）。要改规则本身，就建一个技能目录——
  这样工作流历史里留下的是“用了哪份规则书”，而不是藏在文本框里的内容。

> **安全提示**：技能只是文本指导，节点不会执行技能里的任何东西；但它会作为 system
> 提示词注入，不受信任的技能等于提示注入。第三方技能请当第三方代码对待。

---

## Layout 流水线

MOSS 这类模板把 Layout 拆成“草稿 → 最终”。LLM 的算术不可信，编译器可信。

1. 可选：先设 `width` / `height`。`>0` 表示固定画布——尺寸作为构图约束写进用户消息，Layout 模式下同时是 bbox 的硬边界（`0<=x1<=W`），输出回显这两个数；`0` 表示交给模型决定。
2. 设 `output_format = layout`，节点会在用户消息里附加流水线契约：先出草稿 JSON
   （`width`、`height`、`bbox_coord_space="abs"`、`bbox_format="xyxy"`、`summary`、`items`），
   再另起一行 `CANVAS: WxH`。
3. 节点把 `CANVAS:` 行从正文里摘出来，画布尺寸通过 `size_note` / `width` / `height` 输出。
4. 把提示词正文接进 **Skill Prompt Layout Compiler**。编译器会：
   - 把 `[x0,y0,x1,y1]` 转成 `[y0-H/2, x0-W/2, y1-H/2, x1-W/2]`；
   - 小数边先左/上取整向下、右/下取整向上；
   - 丢弃 schema 外的根字段，校验 `label` 枚举、`text` 项、框面积、越界、16 倍数画布；
   - 输出单行紧凑 JSON + 人类可读的 `status`。

示例（1024×1024，单项 `[100,320,440,760]`）：

```json
{"summary":{...},"items":[{"label":"object","caption":"...","bbox":[-192,-412,248,-72]}],"bbox_coord_space":"abs_centralized","bbox_format":"yxyx"}
```

---

## 参数说明

| 参数 | 含义 |
|---|---|
| `width` / `height` | **既是输入也是输出。** `>0` = 固定画布：尺寸作为硬性构图约束写给模型（Layout 模式下同时是 bbox 边界），输出原样回显。`0` = 自动：由模型决定，尺寸从 `CANVAS:` 行解析。两边要么都填，要么都不填。Layout 模式要求 16 的倍数。 |
| `disable_thinking` | **默认开启。** 发送 `chat_template_kwargs={"enable_thinking": false}`（vLLM / SGLang / llama.cpp server / LM Studio 支持），服务端不认该字段时自动重试并改用提示词 `/no_think`。只有确实想要模型先推理时才关掉——同样的提示词会多花成倍的 token 和时间。 |
| `language` | `English`（默认）/ `中文` / `Bilingual`（两份完整版本） |
| `output_format` | `auto` 由技能自行判断；`caption` / `tag` / `layout` 强制格式 |
| `temperature` | 0.5 是遵循规则的好起点 |
| `top_p` | 0.9 一般够用，很少需要动 |
| `max_tokens` | **要留余量**：思考型模型大半 token 花在隐藏推理上。正文像被截断时，看控制台的 `finish_reason=length` 警告并调大它 |
| `unload_after_run` | **默认开启。** 提示词写完（成功或失败）后请求服务端卸载模型：`POST {root}/models/unload`（llama.cpp router）、`POST {root}/api/v1/models/unload`（LM Studio）、`POST {root}/api/generate` 带 `keep_alive: 0`（Ollama）。云端端点只会返回"无此端点"，不影响结果。连续批量写词时关掉它。 |

---

## 已知边界（不粉饰）

- **上下文**：完整 MOSS 模板约 21k tokens，32k 以下的上下文请用精简版。
- **模型质量**：14B 以下遵循长规则的能力掉得很快，完整模板建议 27B 级起步。
- **延迟**：首次调用要为整份规则书付 prefill；之后能命中服务端前缀缓存就快
  （llama.cpp 系支持，实测 usage 里能看到 `cached_tokens`）。
- **LLM 算术不可信**：坐标换算一律交给编译器。
- **思考型模型**：`disable_thinking` 默认开启，写提示词就该这么用。如果某个端点既不认
  `chat_template_kwargs` 也不认 `/no_think`，把不带标签的推理直接混进 `content`，节点无法区分
  哪段是推理——这种只能在服务端解决（换成非 thinking 版本的模型）。带 `` 标签的块会自动剥掉。
- **不是局部重绘工具**：编译器重算坐标，不修改像素。

---

## 致谢

- 自带技能文本：**MOSS 二次元提示词模板（sfw版）**，作者 是古手梨花sama（B站），逐字收录并署名。
- 架构参考：[ComfyUI_Qwen_H3_Prompt](https://github.com/chflame163/ComfyUI_Qwen_H3_Prompt)（MIT）、
  [ComfyUI-QwenVL](https://github.com/1038lab/ComfyUI-QwenVL)（GPL-3.0）。本项目为独立实现，未复制其代码。

## 许可

MIT（见 `LICENSE`）。自带 MOSS 模板文本的权利归原作者。
