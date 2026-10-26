"""End-to-end check: run the node's core against a real OpenAI-compatible
endpoint, then (for --format layout) compile the returned draft.

Usage:
  python tests/e2e_optimize.py --base-url http://127.0.0.1:11434/v1 \
      --model qwen2.5:14b --skill moss-anime-prompt-slim --format caption
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nodes.layout_compiler import SkillPromptLayoutCompiler  # noqa: E402
from nodes.optimizer import SkillPromptOptimizer  # noqa: E402

HOSHINO = (
    "backless cheongsam, hoshino (blue archive), blue archive, 1girl, heterochromia, "
    "fang, blue eyes, hair between eyes, yellow eyes, pink hair, very long hair, long hair, "
    "ahoge, low twintails, medium breasts, halo, pink halo, looking at viewer, white cheongsam, "
    "full body, high heel sandals, sandals, toe, white sandals, mini cheongsam, short cheongsam, "
    "no bra, no panties, open field, meadow, on petals and grass, sakura tree, sakura in full bloom, "
    "falling petals, (hanafubuki:1.2), blue sky, dappled sunlight, spring vibes, cloud,"
)

POSTER = "咖啡海报：上方大标题「星海咖啡」，左边一个红杯子，右边一个蓝礼盒，奶油色背景。"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--model", default="")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--skill", default="moss-anime-prompt-slim")
    ap.add_argument("--format", default="caption", choices=["auto", "caption", "tag", "layout"])
    ap.add_argument("--language", default="English", choices=["English", "中文", "Bilingual"])
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--prompt-preset", default="hoshino", choices=["hoshino", "poster"])
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--max-tokens", type=int, default=2048)
    args = ap.parse_args()

    prompt = args.prompt or (POSTER if args.prompt_preset == "poster" else HOSHINO)

    node = SkillPromptOptimizer()
    text, size_note, width, height = node.optimize(
        prompt=prompt,
        skill=args.skill,
        custom_skill="",
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        language=args.language,
        output_format=args.format,
        temperature=0.5,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        extra_instruction="",
    )

    print("\n===== OPTIMIZED PROMPT =====\n")
    print(text)
    print("\n===== SIZE NOTE =====")
    print(size_note or "(none)")

    if args.format == "layout":
        compiler = SkillPromptLayoutCompiler()
        final_json, status = compiler.compile(text, width or 1024, height or 1024)
        print("\n===== COMPILED LAYOUT (one line) =====\n")
        print(final_json)
        print("\n===== STATUS =====\n")
        print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
