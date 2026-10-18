---
license: mit
base_model:
- facebook/nllb-200-distilled-600M
- facebook/nllb-200-distilled-1.3B
tags:
- peft
- lora
- machine-translation
- nllb-200
- reinforcement-learning
- grpo
---

# Reference-Free RL Fine-Tuning for MT — LoRA Adapters

LoRA adapters (rank 16, `q_proj`/`v_proj`) from **"Reference-Free Reinforcement Learning
Fine-Tuning for MT: A Seq2Seq Perspective"**, applying GRPO to NLLB-200 (600M/1.3B) with
a reference-free reward (LaBSE + COMET-Kiwi). Code: https://github.com/erngarcia/reference-free-ft-rl-mt

Every folder here corresponds to one training run's *best* intermediate checkpoint
(highest intermediate chrF++ on a held-out dev subset), renamed from the code's own
`adapters_best/` to `adapters/` for clarity. The directory structure mirrors the
project's own `results/` layout — see the code repo's README for what each run tag
(`exp_a_*`, `exp_b_*`, `cascade_*`, `ccnews_scaling_*`, `data_size_ablation_*`, etc.)
means.

## Loading an adapter

```python
from peft import PeftModel
from transformers import AutoModelForSeq2SeqLM

base = AutoModelForSeq2SeqLM.from_pretrained("facebook/nllb-200-distilled-600M")
adapter = PeftModel.from_pretrained(
    base,
    "ergar/monolingual-reinforcement-learning-mt",
    subfolder="results/exp_a_600m_en_arb_Arab/adapters/arb_Arab",
)
```

Swap the `subfolder` path and base model (600M vs. 1.3B — check the run tag) for any
other language/condition in the repo.

## Scope

This repo excludes `results/legacy_original_submission/` adapters (superseded by this
project's rerun where applicable — see the code repo's own note on that directory).
