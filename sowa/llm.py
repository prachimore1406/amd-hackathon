from __future__ import annotations

import json
import traceback


def _log(message: str) -> None:
    print(f"[SOWA LLM] {message}", flush=True)


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
    except ImportError as exc:
        _log(f"Optional LLM dependencies unavailable, using fallback scheduler: {exc}")
        return FallbackLLM()

    try:
        model_id = "Qwen/Qwen2.5-7B-Instruct"
        use_accelerator = torch.cuda.is_available()
        device = 0 if use_accelerator else -1
        torch_dtype = torch.float16 if use_accelerator else torch.float32
        _log(
            f"Initializing {model_id} "
            f"(accelerator={'yes' if use_accelerator else 'no'}, device={device})"
        )

        pipe = pipeline(
            "text-generation",
            model=model_id,
            device=device,
            max_new_tokens=250,
            temperature=0.2,
            torch_dtype=torch_dtype,
            return_full_text=False,
        )
        _log("Model pipeline initialized successfully.")
        return HuggingFacePipeline(pipeline=pipe)
    except Exception as exc:
        _log(f"Model initialization failed, falling back to rule-based scheduler: {exc}")
        _log(traceback.format_exc())
        return FallbackLLM()


class LazyLLM:
    """Defer expensive model initialization until the first inference call."""

    def __init__(self):
        self._client = None

    def invoke(self, prompt_input):
        if self._client is None:
            _log("First inference requested; loading model client now.")
            self._client = _build_llm()
        response = self._client.invoke(prompt_input)
        _log(f"Inference completed using {self._client.__class__.__name__}.")
        return response


llm = LazyLLM()
