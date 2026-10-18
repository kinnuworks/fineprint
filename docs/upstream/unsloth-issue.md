# Draft issue for unslothai/unsloth (not posted)

**Title:** Model card template sets `license: apache-2.0` on every upload, including Llama, Gemma and Qwen Research fine-tunes

`MODEL_CARD` in `unsloth/save.py` (checked at 72d0d2d) writes `license: apache-2.0` and `**License:** apache-2.0` for every model pushed through `push_to_hub`, `push_to_hub_merged` and the related helpers. The base model's license isn't consulted.

When the base is Llama 3.x, Gemma or Qwen Research, the derivative's card then says apache-2.0 while the base license still applies to it. Llama 3.1's license, for example, asks derivatives to ship a copy of the agreement and start their name with "Llama"; Qwen Research is non-commercial.

How common this is: we loaded the metadata of all 3.16M public models on the Hub into a graph. Of the 48,975 models whose declared license is permissive while a model they declare as a base carries restricted terms, 26,406 have the tag set this template writes (`unsloth`, `text-generation-inference`, `license:apache-2.0`). Method and counts: link to the FinePrint repo once public.

Proposed change (patch attached): read the license from the base model's card (following `unsloth/` mirrors up to the original), copy `license_name` and `license_link` when the base uses `license: other`, and fall back to `license: other` instead of `apache-2.0` when the license can't be read. Four `MODEL_CARD.format(...)` call sites in `unsloth/save.py` and three in `studio/backend/core/export/export.py` (which has its own copy of the template) get one extra argument; no other behaviour changes. The existing card tests lift the new helper with the functions they already test, and six new tests cover the base license, the mirror walk and the `other` fallback. `tests/test_upload_model_card_method.py`, `tests/test_merged_hub_destination.py` and `studio/backend/tests/test_export_hub_push.py` pass, with no network access.

Happy to adjust the approach if you'd rather handle it another way.
