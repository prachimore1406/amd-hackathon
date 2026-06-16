from __future__ import annotations

import json


class FallbackLLM:
    """Rule-based fallback used when optional LLM dependencies are unavailable."""

    def invoke(self, prompt_input):
        prompt_text = prompt_input if isinstance(prompt_input, str) else str(prompt_input)
        prompt_lower = prompt_text.lower()

        if "ml training" in prompt_lower:
            decision = "AMD-Instinct-GPU"
            risk_level = "Medium"
            reasoning = "Selected the GPU node because the workload is ML training and the fallback scheduler prioritizes accelerator hardware."
        elif "web serving" in prompt_lower:
            decision = "AMD-EPYC-CPU"
            risk_level = "Low"
            reasoning = "Selected the EPYC CPU node because the workload is web serving and benefits from predictable CPU performance."
        else:
            decision = "General-VM"
            risk_level = "Low"
            reasoning = "Selected the general-purpose node because the workload does not require specialized hardware."

        return json.dumps(
            {
                "reasoning": reasoning,
                "decision": decision,
                "risk_level": risk_level,
                "performance_explanation": "Used the deterministic fallback scheduler because the configured LLM runtime is unavailable.",
                "tool_trace_summary": "FallbackLLM",
            }
        )


def _build_llm():
    try:
        import torch
        from langchain_huggingface import HuggingFacePipeline
        from transformers import pipeline
    except ImportError:
        return FallbackLLM()

    print("Initializing Qwen2.5-7B on AMD MI 350 X (ROCm)...")
    model_id = "Qwen/Qwen2.5-7B-Instruct"
    use_accelerator = torch.cuda.is_available()
    device = 0 if use_accelerator else -1
    torch_dtype = torch.float16 if use_accelerator else torch.float32

    pipe = pipeline(
        "text-generation",
        model=model_id,
        device=device,
        max_new_tokens=250,
        temperature=0.2,
        torch_dtype=torch_dtype,
    )
    return HuggingFacePipeline(pipeline=pipe)


class LazyLLM:
    """Defer expensive model initialization until the first inference call."""

    def __init__(self):
        self._client = None

    def invoke(self, prompt_input):
        if self._client is None:
            self._client = _build_llm()
        return self._client.invoke(prompt_input)


llm = LazyLLM()
