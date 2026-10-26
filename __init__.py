"""ComfyUI_SkillPrompt — LLM + markdown skill -> structured positive prompt."""

from .nodes.layout_compiler import SkillPromptLayoutCompiler
from .nodes.optimizer import SkillPromptOptimizer, SkillPromptOptimizerLlamaCpp

NODE_CLASS_MAPPINGS = {
    "SkillPromptOptimizer": SkillPromptOptimizer,
    "SkillPromptOptimizerLlamaCpp": SkillPromptOptimizerLlamaCpp,
    "SkillPromptLayoutCompiler": SkillPromptLayoutCompiler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SkillPromptOptimizer": "Skill Prompt Optimizer",
    "SkillPromptOptimizerLlamaCpp": "Skill Prompt Optimizer (llama.cpp)",
    "SkillPromptLayoutCompiler": "Skill Prompt Layout Compiler",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
