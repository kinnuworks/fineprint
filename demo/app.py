"""A small chat service. FinePrint's CI check fails on it: the model below is BLOCK for commercial use."""
from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit")
model = AutoModelForCausalLM.from_pretrained("unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit", device_map="auto")


def reply(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
    out = model.generate(inputs, max_new_tokens=200)
    return tokenizer.decode(out[0][inputs.shape[-1]:], skip_special_tokens=True)


if __name__ == "__main__":
    print(reply("Write one sentence about license terms."))
