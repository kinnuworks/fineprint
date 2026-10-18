---
language:
- en
- id
license: apache-2.0
tags:
- unsloth
- gemma-2
- effort-estimation
- software-engineering
- trl
- sft
- bilingual
datasets:
- custom
base_model: unsloth/gemma-2-2b-it-bnb-4bit
---

# JOSSE Gemma 2 Effort Estimator

This model is fine-tuned from Gemma 2 2B Instruct for **software development effort estimation**.

## Model Description

- **Base Model:** Gemma 2 2B Instruct (4-bit quantized)
- **Fine-tuned on:** 43,288 bilingual samples (English & Indonesian)
- **Task:** Estimate development effort (in hours) for software engineering tasks
- **Languages:** English and Indonesian

## Training Details

- **Framework:** Unsloth + TRL
- **Method:** LoRA (Low-Rank Adaptation)
- **LoRA Rank:** 32
- **Training Samples:** ~38,959 (90% of dataset)
- **Validation Samples:** ~4,329 (10% of dataset)
- **Training Time:** ~2-4 hours on T4 GPU

## Usage

### Direct Python

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "Ozin11/josse-gemma2-effort-estimator"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
Estimate the effort required to complete this task.

### Input:
Fix authentication bug in login module

### Response:
"""

inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=100)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```

### Hugging Face Inference API

```python
import requests

API_URL = "https://api-inference.huggingface.co/models/Ozin11/josse-gemma2-effort-estimator"
headers = {"Authorization": "Bearer YOUR_HF_TOKEN"}

def estimate_effort(task_description):
    payload = {
        "inputs": f"Estimate the effort required to complete this task.\n\nInput: {task_description}\n\nResponse:",
        "parameters": {"max_new_tokens": 100}
    }
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()

result = estimate_effort("Implement REST API for user management")
print(result)
```

## Example Outputs

**English:**
- Input: "Fix authentication bug in login module"
- Output: "Estimated effort: 1.5 hours"

**Indonesian:**
- Input: "perbaiki bug autentikasi pada modul login"
- Output: "Perkiraan usaha: 1.5 jam"

## Limitations

- Estimates are based on training data patterns
- May not account for specific project complexities
- Should be used as a reference, not absolute truth

## License

Apache 2.0 (following Gemma 2 license)

## Citation

```bibtex
@misc{josse-gemma2-effort-estimator,
  author = {Ozin11},
  title = {JOSSE Gemma 2 Effort Estimator},
  year = {2026},
  publisher = {Hugging Face},
  url = {https://huggingface.co/Ozin11/josse-gemma2-effort-estimator}
}
```
