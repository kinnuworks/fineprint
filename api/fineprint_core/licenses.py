"""License library: which declared licenses carry terms down to derivatives,
and the clauses that create each obligation.

Quotes are kept short and always link to the full text.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Clause:
    code: str
    obligation: str
    quote: str
    source: str
    tier: str = "contractual"  # contractual | contested


@dataclass(frozen=True)
class License:
    key: str
    family: str
    clauses: tuple[Clause, ...] = field(default_factory=tuple)
    commercial: bool = True  # False: commercial use needs a separate license


LLAMA31 = "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/blob/main/LICENSE"
LLAMA32 = "https://huggingface.co/meta-llama/Llama-3.2-11B-Vision-Instruct/blob/main/LICENSE.txt"
LLAMA3 = "https://huggingface.co/meta-llama/Meta-Llama-3-8B/blob/main/LICENSE"
LLAMA2 = "https://huggingface.co/meta-llama/Llama-2-7b/blob/main/LICENSE.txt"
GEMMA = "https://ai.google.dev/gemma/terms"
CCBYNC = "https://creativecommons.org/licenses/by-nc/4.0/legalcode"
FLUXDEV = "https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md"
QWENRES = "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE"
QWEN = "https://huggingface.co/Qwen/Qwen2.5-72B-Instruct/blob/main/LICENSE"
MNPL = "https://mistral.ai/licences/MNPL-0.1.md"
DEEPSEEK = "https://huggingface.co/deepseek-ai/DeepSeek-V3/blob/main/LICENSE-MODEL"
NAMED_NC = "named-non-commercial"
NAMED_RESEARCH = "named-research-only"


def _llama3x(version: str, source: str, brand: str, prefix: str) -> tuple[Clause, ...]:
    return (
        Clause(f"llama{version}-1bi-a", "Ship a copy of the license agreement with the model.",
               "provide a copy of this Agreement with any such Llama Materials", source),
        Clause(f"llama{version}-1bi-b", f'Display "{brand}" on a related website, interface or post.',
               f'prominently display "{brand}"', source),
        Clause(f"llama{version}-1bi-c", f'Start the model name with "{prefix}".',
               f'include "{prefix}" at the beginning of any such AI model name', source),
        Clause(f"llama{version}-2", "A separate license from Meta is needed above 700M monthly active users.",
               "greater than 700 million monthly active users", source),
        Clause(f"llama{version}-aup", "Use stays bound by Meta's Acceptable Use Policy.",
               "Acceptable Use Policy", source),
    )


LICENSES: dict[str, License] = {
    "llama2": License("llama2", "Llama 2", (
        Clause("llama2-1bi", "Give recipients a copy of the license agreement.",
               "you shall provide a copy of this Agreement to such third party", LLAMA2),
        Clause("llama2-1biii", 'Keep the "Llama 2 is licensed under the LLAMA 2 Community License" notice file.',
               'within a "Notice" text file distributed as a part of such copies', LLAMA2),
        Clause("llama2-2", "A separate license from Meta is needed above 700M monthly active users.",
               "greater than 700 million monthly active users", LLAMA2),
    )),
    "llama3": License("llama3", "Llama 3", _llama3x("3", LLAMA3, "Built with Meta Llama 3", "Llama 3")),
    "llama3.1": License("llama3.1", "Llama 3.1", _llama3x("3.1", LLAMA31, "Built with Llama", "Llama")),
    "llama3.2": License("llama3.2", "Llama 3.2", _llama3x("3.2", LLAMA32, "Built with Llama", "Llama")),
    "llama3.3": License("llama3.3", "Llama 3.3", _llama3x("3.3", "https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct/blob/main/LICENSE", "Built with Llama", "Llama")),
    "gemma": License("gemma", "Gemma", (
        Clause("gemma-3.1-1", "Pass Gemma's use restrictions on as an enforceable term, and tell recipients.",
               "include the use restrictions referenced in Section 3.2 as an enforceable provision", GEMMA),
        Clause("gemma-3.1-2", "Give recipients a copy of the Gemma Terms of Use.",
               "provide all third party recipients of Gemma or Model Derivatives a copy", GEMMA),
        Clause("gemma-3.1-3", "Mark modified files as modified.",
               "cause any modified files to carry prominent notices", GEMMA),
        Clause("gemma-3.1-4", 'Ship a "Notice" file pointing to the Gemma Terms of Use.',
               'must be accompanied by a "Notice" text file', GEMMA),
    )),
}

LICENSES["flux-1-dev-non-commercial-license"] = License("flux-1-dev-non-commercial-license", "FLUX.1 [dev] Non-Commercial", (
    Clause("flux-dev-2a", "Non-commercial use only, for the model and anything derived from it.",
           "solely for your Non-Commercial Purposes", FLUXDEV),
    Clause("flux-dev-2a-deriv", "The same restrictions apply to every derivative.",
           "also apply to any Derivative you create", FLUXDEV),
    Clause("flux-dev-3a", "Give recipients a copy of the license.",
           "make available a copy of this License to third-party recipients", FLUXDEV),
    Clause("flux-dev-3c", "State that you modified the model in the attribution notice.",
           "a statement that you have modified", FLUXDEV),
), commercial=False)
for _k in ("qwen-research", "tongyi-qianwen-research"):
    LICENSES[_k] = License(_k, "Qwen Research", (
        Clause(f"{_k}-2a", "Non-commercial use only (research or evaluation).", "FOR NON-COMMERCIAL PURPOSES ONLY", QWENRES),
        Clause(f"{_k}-3a", "Give recipients a copy of the agreement.", "a copy of this Agreement", QWENRES),
        Clause(f"{_k}-4b", 'Show "Built with Qwen" or "Improved using Qwen" for derived models.',
               "Built with Qwen", QWENRES),
    ), commercial=False)
for _k in ("qwen", "tongyi-qianwen"):
    LICENSES[_k] = License(_k, "Qwen", (
        Clause(f"{_k}-3a", "Give recipients a copy of the agreement.", "a copy of this Agreement", QWEN),
        Clause(f"{_k}-4", "A separate license is needed above 100M monthly active users.",
               "more than 100 million monthly active users", QWEN),
        Clause(f"{_k}-5b", 'Show "Built with Qwen" or "Improved using Qwen" in product documentation.',
               "Built with Qwen", QWEN),
    ))
for _k in ("mnpl", "mrl"):
    LICENSES[_k] = License(_k, "Mistral Non-Production" if _k == "mnpl" else "Mistral Research", (
        Clause(f"{_k}-3.2", "Testing, research or personal use only; no commercial supply.",
               "shall not supply the Mistral Models or Derivatives in the course of a commercial activity",
               MNPL if _k == "mnpl" else "https://mistral.ai/licenses/MRL-0.1.md"),
        Clause(f"{_k}-2.2", "Give recipients a copy of the agreement and keep the notice file.",
               "You must make available a copy of this Agreement", MNPL if _k == "mnpl" else "https://mistral.ai/licenses/MRL-0.1.md"),
    ), commercial=False)
OPENRAIL = "https://huggingface.co/blog/open_rail"
for _k in ("openrail", "openrail++", "creativeml-openrail-m", "bigscience-openrail-m", "bigscience-bloom-rail-1.0", "bigcode-openrail-m"):
    LICENSES[_k] = License(_k, "OpenRAIL", (
        Clause(f"{_k}-use", "Use restrictions in the license attachment travel with the model and every derivative.",
               "use-based restrictions", OPENRAIL),
        Clause(f"{_k}-pass", "Pass the same use restrictions on to anyone you distribute to.",
               "include those use restrictions", OPENRAIL),
    ))
LICENSES["llama4"] = License("llama4", "Llama 4", _llama3x("4", "https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct", "Built with Llama", "Llama"))
_NC_NAMED = {
    "flux-non-commercial-license": ("FLUX Non-Commercial", "https://huggingface.co/black-forest-labs/FLUX.2-dev"),
    "coqui-public-model-license": ("Coqui Public Model License", "https://coqui.ai/cpml"),
    "apple-amlr": ("Apple Machine Learning Research", "https://huggingface.co/apple"),
    "circlestone-labs-non-commercial-license": ("Circlestone Labs Non-Commercial", "https://huggingface.co/circlestone-labs"),
}
for _k, (_fam, _src) in _NC_NAMED.items():
    LICENSES[_k] = License(_k, _fam, (
        Clause(f"{_k}-nc", "Non-commercial use only, as the license name states; read the full text before any other use.",
               _k, _src),
    ), commercial=False)
LICENSES["deepseek"] = License("deepseek", "DeepSeek", (
    Clause("deepseek-use", "Use restrictions in the license attachment travel with the model and every derivative.",
           "use-based restrictions", DEEPSEEK),
    Clause("deepseek-copy", "Give recipients a copy of the license.", "a copy of this License", DEEPSEEK),
))
LICENSES[NAMED_NC] = License(NAMED_NC, "Named non-commercial license", (
    Clause("named-nc", "The license name says non-commercial; treat it as non-commercial until the full text is read.",
           "non-commercial", "https://huggingface.co/docs/hub/repositories-licenses"),
), commercial=False)
LICENSES[NAMED_RESEARCH] = License(NAMED_RESEARCH, "Named research license", (
    Clause("named-research", "The license name says research; treat it as research-only until the full text is read.",
           "research", "https://huggingface.co/docs/hub/repositories-licenses"),
), commercial=False)
LICENSES["research-only"] = License("research-only", "Research only", (
    Clause("research-only", "Research use only, as stated by the uploader.", "research-only", "https://huggingface.co/docs/hub/repositories-licenses"),
), commercial=False)
ALIASES = {"gemma-terms-of-use": "gemma", "llama3": "llama3", "llama-3": "llama3", "llama3.1": "llama3.1",
           "llama-3.1": "llama3.1", "llama3.2": "llama3.2", "llama3.3": "llama3.3", "llama2": "llama2",
           "llama-4": "llama4", "flux1-dev-non-commercial-license": "flux-1-dev-non-commercial-license",
           "flux.1-dev-non-commercial-license": "flux-1-dev-non-commercial-license",
           "flux-dev-non-commercial-license": "flux-1-dev-non-commercial-license",
           "qwen-research-license": "qwen-research", "tongyi-qianwen-research-license": "tongyi-qianwen-research",
           "tongyi-qianwen-license-agreement": "tongyi-qianwen",
           "mistral-ai-research-licence": "mrl", "mistral-research-license": "mrl", "deepseek-license": "deepseek"}


for _k in ("cc-by-nc-4.0", "cc-by-nc-sa-4.0", "cc-by-nc-nd-4.0", "cc-by-nc-2.0", "cc-by-nc-3.0", "cc-by-nc-sa-3.0"):
    LICENSES[_k] = License(_k, "CC BY-NC", (
        Clause(f"{_k}-nc", "Non-commercial use only.", "NonCommercial", CCBYNC),
        Clause(f"{_k}-by", "Credit the original creator.", "Attribution", CCBYNC),
    ), commercial=False)

PERMISSIVE = {
    "apache-2.0", "mit", "bsd", "bsd-2-clause", "bsd-3-clause", "afl-3.0", "unlicense", "wtfpl",
    "cc0-1.0", "cc-by-4.0", "isc", "zlib", "bsl-1.0",
}
UNKNOWN = {"", "other", "unknown", None}


def effective(license: str | None, license_name: str | None = None) -> str:
    """The license that applies.

    The declared tag, or, when the tag is empty or `other`, the named license from the card,
    normalised through ALIASES. Unknown names that say non-commercial or research are mapped to
    a non-commercial family so they fail closed.
    """
    import re
    lic = (license or "").strip().lower()
    if lic in ("", "other") and license_name:
        name = license_name.strip().lower()
        name = ALIASES.get(name, name)
        if name in LICENSES or name in PERMISSIVE:
            return name
        if re.search(r"non-?commercial|noncommercial|(^|[-_.])nc([-_.]|$)|non-commercial-only", name):
            return NAMED_NC
        if "research" in name:
            return NAMED_RESEARCH
        return name
    return lic


def recognized(key: str | None) -> bool:
    return (key or "") in PERMISSIVE or (key or "") in LICENSES


def restrictive(key: str | None) -> License | None:
    return LICENSES.get(key or "")
