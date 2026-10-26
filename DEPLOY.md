# 部署与自测清单

## 1. 拷到 ComfyUI

Windows（在能访问 A 机的机器上执行；路径按你的实际安装改）：

```bat
robocopy "D:\Hermes\projects\ComfyUI_SkillPrompt" "\\192.168.51.14\D$\GAME\ComfyUI\ComfyUI\custom_nodes\ComfyUI_SkillPrompt" /E /XD .git __pycache__
```

在 A 本机上则直接：

```bat
robocopy "D:\Hermes\projects\ComfyUI_SkillPrompt" "D:\GAME\ComfyUI\ComfyUI\custom_nodes\ComfyUI_SkillPrompt" /E /XD .git __pycache__
```

> `.git` 和 `__pycache__` 不拷也行；代码只依赖标准库。

## 2. 重启 ComfyUI

自定义节点在启动时导入，必须重启进程（刷新浏览器不算）。

## 3. 确认节点出现

右键菜单 → `SkillPrompt` 分类下应有三个：

- `Skill Prompt Optimizer`（HTTP）
- `Skill Prompt Optimizer (llama.cpp)`
- `Skill Prompt Layout Compiler`

启动日志里应该能看到一条 `[SkillPrompt] skills: ...`（首次建下拉框时扫描）。

## 4. 五分钟自测

打开 `example_workflows/skillprompt_moss_basic.json`，改两处：

| 字段 | 改成 |
|---|---|
| Checkpoint | 你机器上实际有的 |
| `base_url` | `http://127.0.0.1:8491/v1`（A 机自己的 router） |
| `model` | `Ukisai-Swift-1.5-Qwen3.8-27B-Q6_K_L-MTP` |
| `disable_thinking` | 保持 `true`（关掉思考，输出才是干净的提示词） |

然后 Queue。控制台应出现：

```
[SkillPrompt] skill=moss-anime-prompt-slim (~3892 tok) est_tokens≈...
[SkillPrompt] usage={'completion_tokens': ..., 'prompt_tokens': ..., 'finish_reason': 'stop'}
```

## 5. 出问题时看哪儿

| 现象 | 大概率原因 | 处理 |
|---|---|---|
| 节点没出现在菜单里 | 导入失败 | 看 ComfyUI 启动日志的 Traceback，把最后 20 行发我 |
| `skills` 下拉框是占位符 `(no skill found...)` | `skills/` 没拷全 | 确认 `custom_nodes/ComfyUI_SkillPrompt/skills/moss-anime-prompt/SKILL.md` 存在 |
| 报“连不上” | router 端口/模型名不对 | `curl http://127.0.0.1:8491/v1/models` 先确认 |
| 正文写到一半停了 | max_tokens 被隐藏推理吃掉 | 看有没有 `finish_reason=length` 警告，把 max_tokens 调到 4096 |
| `HTTP 400 context length` | 完整版 skill 塞不下 | 换 `moss-anime-prompt-slim` |
| Layout 编译报“不是 16 的倍数” | 模型给了 1000×1500 之类 | 把 width/height 改成 1024×1536 |

## 6. 想验 Layout 编译器

`output_format` 设 `layout`，提示词写“咖啡海报：上方标题「星海咖啡」，左边红杯，右边蓝礼盒”。
第二个节点的 `text` 接第一个节点的 `optimized_prompt`，`width`/`height` 接它的同名输出。

期望：`layout_json` 是一行紧凑 JSON，根字段只有 `summary` / `items` / `bbox_coord_space` / `bbox_format`；
`status` 以 `已编译：画布 1024x1024，N 项` 开头。
