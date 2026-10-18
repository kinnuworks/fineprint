---
license: apache-2.0
base_model: Nimbz/Gemma-4-Gembrain-X-31B
tags:
- merge
- mergekit
- reasoning
- roleplay
- creative writing
- image-prompt-generation
- general purpose
- uncensored
- conversational
- 31B
- gemma-4
- mlx
- mlx-my-repo
---

# ailexleon/Gemma-4-Gembrain-X-31B-mlx-8Bit

The Model [ailexleon/Gemma-4-Gembrain-X-31B-mlx-8Bit](https://huggingface.co/ailexleon/Gemma-4-Gembrain-X-31B-mlx-8Bit) was converted to MLX format from [Nimbz/Gemma-4-Gembrain-X-31B](https://huggingface.co/Nimbz/Gemma-4-Gembrain-X-31B) using mlx-lm version **0.31.2**.

## Use with mlx

```bash
pip install mlx-lm
```

```python
from mlx_lm import load, generate

model, tokenizer = load("ailexleon/Gemma-4-Gembrain-X-31B-mlx-8Bit")

prompt="hello"

if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template is not None:
    messages = [{"role": "user", "content": prompt}]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

response = generate(model, tokenizer, prompt=prompt, verbose=True)
```
