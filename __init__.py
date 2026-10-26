"""ComfyUI_SkillPrompt — LLM + markdown skill -> structured positive prompt."""

from .nodes.layout_compiler import SkillPromptLayoutCompiler
from .nodes.optimizer import SkillPromptOptimizer, SkillPromptOptimizerAdvanced

NODE_CLASS_MAPPINGS = {
    "SkillPromptOptimizer": SkillPromptOptimizer,
    "SkillPromptOptimizerAdvanced": SkillPromptOptimizerAdvanced,
    "SkillPromptLayoutCompiler": SkillPromptLayoutCompiler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SkillPromptOptimizer": "Skill Prompt Optimizer",
    "SkillPromptOptimizerAdvanced": "Skill Prompt Optimizer (Advanced)",
    "SkillPromptLayoutCompiler": "Skill Prompt Layout Compiler",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
