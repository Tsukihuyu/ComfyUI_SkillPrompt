# 部署与自测

## 1. 放进 custom_nodes

```bash
cd ComfyUI/custom_nodes
git clone <repository-url> ComfyUI_SkillPrompt
cd ComfyUI_SkillPrompt
cp skillprompt.ini.example skillprompt.ini
```

然后编辑 `skillprompt.ini`，至少填一段：

```ini
[local-llamacpp]
name = local llama.cpp
base_url = http://127.0.0.1:8491/v1
model = YOUR-MODEL-NAME
```

## 2. 准备一个技能

`skills/` 里默认是空的（本仓库不附带提示词文本）。新建：

```
skills/my-rules/SKILL.md
```

内容就是你的写词规则书，见 `skills/README.md` 里的最小骨架。

## 3. 重启 ComfyUI

自定义节点在启动时导入，必须重启进程（刷新浏览器不算）。

## 4. 确认节点出现

右键菜单 → `SkillPrompt` 分类下应有两个：

- `Skill Prompt Optimizer`
- `Skill Prompt Layout Compiler`

检查点：

| 项 | 期望 |
|---|---|
| `llm_model` 下拉框 | 列出 `skillprompt.ini` 里的段；只有 `(no endpoint configured - edit skillprompt.ini)` 说明 ini 没填 |
| `skill` 下拉框 | 列出 `skills/` 下的文件夹；只有占位符说明没有放 `SKILL.md` |

## 5. 五分钟自测

1. `prompt` 里写：「一个穿红裙的女孩站在雨夜巷口，路灯是橘色的」。
2. `output_format` 选 `caption`，`language` 选 `English`，其余默认。
3. 运行。控制台应出现：

```
[SkillPrompt] endpoint=... model=...
[SkillPrompt] skill=... (~N tok) est_tokens≈... format=caption lang=English canvas=auto
[SkillPrompt] usage={... 'finish_reason': 'stop'}
[SkillPrompt] 已释放显存：...
```

4. 把 `optimized_prompt` 接到 `CLIPTextEncode`，下游正常出图。

## 6. 出问题时看哪儿

| 现象 | 大概率原因 | 处理 |
|---|---|---|
| 节点没出现在菜单里 | 导入失败 | 看 ComfyUI 启动日志最后的 Traceback |
| `llm_model` 只有占位符 | ini 不存在或没有有效段 | 确认 `skillprompt.ini` 在同一目录，段里同时有 `base_url` 和 `model` |
| `skill` 只有占位符 | `skills/` 里没有 `SKILL.md` | 建 `skills/<名称>/SKILL.md` |
| 报“连不上” | 端点没起 / 端口错 | `curl <base_url>/models` 先确认 |
| 报 HTTP 400 context | 规则书太长，模型上下文不够 | 换更短的技能，或换大上下文模型 |
| 正文写到一半停了 | `max_tokens` 被隐藏推理吃掉 | 看 `finish_reason=length` 警告，调大 `max_tokens`，或打开 `disable_thinking` |
| 还在输出思考过程 | 端点既不吃 `chat_template_kwargs` 也不吃 `/no_think` | 在服务端换成非 thinking 模型 |
| 出图 OOM | 模型没卸载 | 确认 `unload_after_run=true`，并看控制台的卸载回执 |
| Layout 编译报“不是 16 的倍数” | 画布尺寸不对 | 改成 1024×1024 / 1536×1024 / 1024×1536 之类 |
| 改了 ini 不生效 | 没有重启 | 重启 ComfyUI |

## 7. 命令行的等价检查

不需要开着 ComfyUI，也能验端点与技能是否配好：

```bash
python tests/e2e_optimize.py --list
python tests/e2e_optimize.py --profile "local llama.cpp" --format caption
```
