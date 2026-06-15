import torch
from langchain_huggingface import HuggingFacePipeline
from transformers import pipeline

print("Initializing Qwen2.5-7B on AMD MI 350 X (ROCm)...")
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
USE_ACCELERATOR = torch.cuda.is_available()
DEVICE = 0 if USE_ACCELERATOR else -1
TORCH_DTYPE = torch.float16 if USE_ACCELERATOR else torch.float32

pipe = pipeline(
    "text-generation",
    model=MODEL_ID,
    device=DEVICE,
    max_new_tokens=250,
    temperature=0.2,
    torch_dtype=TORCH_DTYPE,
)
llm = HuggingFacePipeline(pipeline=pipe)
