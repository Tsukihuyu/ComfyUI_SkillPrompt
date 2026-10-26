"""ComfyUI_SkillPrompt — LLM + markdown skill -> structured positive prompt."""

from .nodes.layout_compiler import SkillPromptLayoutCompiler
from .nodes.optimizer import (
    SkillPromptOptimizer,
    SkillPromptOptimizerAdvanced,
    SkillPromptOptimizerLlamaCpp,
    SkillPromptOptimizerLlamaCppAdvanced,
)

NODE_CLASS_MAPPINGS = {
    "SkillPromptOptimizer": SkillPromptOptimizer,
    "SkillPromptOptimizerAdvanced": SkillPromptOptimizerAdvanced,
    "SkillPromptOptimizerLlamaCpp": SkillPromptOptimizerLlamaCpp,
    "SkillPromptOptimizerLlamaCppAdvanced": SkillPromptOptimizerLlamaCppAdvanced,
    "SkillPromptLayoutCompiler": SkillPromptLayoutCompiler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SkillPromptOptimizer": "Skill Prompt Optimizer",
    "SkillPromptOptimizerAdvanced": "Skill Prompt Optimizer (Advanced)",
    "SkillPromptOptimizerLlamaCpp": "Skill Prompt Optimizer (llama.cpp)",
    "SkillPromptOptimizerLlamaCppAdvanced": "Skill Prompt Optimizer (llama.cpp Advanced)",
    "SkillPromptLayoutCompiler": "Skill Prompt Layout Compiler",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
