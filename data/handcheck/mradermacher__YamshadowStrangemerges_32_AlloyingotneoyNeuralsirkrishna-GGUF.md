---
base_model: MaziyarPanahi/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna
language:
- en
library_name: transformers
license: apache-2.0
model_creator: MaziyarPanahi
model_name: YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna
quantized_by: mradermacher
tags:
- Safetensors
- text-generation-inference
- merge
---
## About

<!-- ### quantize_version: 2 -->
<!-- ### output_tensor_quantised: 1 -->
<!-- ### convert_type: hf -->
<!-- ### vocab_type:  -->
<!-- ### tags: nicoboss -->
static quants of https://huggingface.co/MaziyarPanahi/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna

<!-- provided-files -->
weighted/imatrix quants seem not to be available (by me) at this time. If they do not show up a week or so after the static ones, I have probably not planned for them. Feel free to request them by opening a Community Discussion.
## Usage

If you are unsure how to use GGUF files, refer to one of [TheBloke's
READMEs](https://huggingface.co/TheBloke/KafkaLM-70B-German-V0.1-GGUF) for
more details, including on how to concatenate multi-part files.

## Provided Quants

(sorted by size, not necessarily quality. IQ-quants are often preferable over similar sized non-IQ quants)

| Link | Type | Size/GB | Notes |
|:-----|:-----|--------:|:------|
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q2_K.gguf) | Q2_K | 2.8 |  |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q3_K_S.gguf) | Q3_K_S | 3.3 |  |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q3_K_M.gguf) | Q3_K_M | 3.6 | lower quality |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q3_K_L.gguf) | Q3_K_L | 3.9 |  |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.IQ4_XS.gguf) | IQ4_XS | 4.0 |  |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q4_K_S.gguf) | Q4_K_S | 4.2 | fast, recommended |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q4_K_M.gguf) | Q4_K_M | 4.5 | fast, recommended |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q5_K_S.gguf) | Q5_K_S | 5.1 |  |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q5_K_M.gguf) | Q5_K_M | 5.2 |  |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q6_K.gguf) | Q6_K | 6.0 | very good quality |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.Q8_0.gguf) | Q8_0 | 7.8 | fast, best quality |
| [GGUF](https://huggingface.co/mradermacher/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna-GGUF/resolve/main/YamshadowStrangemerges_32_AlloyingotneoyNeuralsirkrishna.f16.gguf) | f16 | 14.6 | 16 bpw, overkill |

Here is a handy graph by ikawrakow comparing some lower-quality quant
types (lower is better):

![image.png](https://www.nethype.de/huggingface_embed/quantpplgraph.png)

And here are Artefact2's thoughts on the matter:
https://gist.github.com/Artefact2/b5f810600771265fc1e39442288e8ec9

## FAQ / Model Request

See https://huggingface.co/mradermacher/model_requests for some answers to
questions you might have and/or if you want some other model quantized.

## Thanks

I thank my company, [nethype GmbH](https://www.nethype.de/), for letting
me use its servers and providing upgrades to my workstation to enable
this work in my free time. Additional thanks to [@nicoboss](https://huggingface.co/nicoboss) for giving me access to his private supercomputer, enabling me to provide many more imatrix quants, at much higher quality, than I would otherwise be able to.

<!-- end -->
