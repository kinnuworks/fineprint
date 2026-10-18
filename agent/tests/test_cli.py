import json

import httpx

import pytest

from fineprint import cli, client
from fineprint.scan import scan

FANAR = "QCRI/Fanar-2-27B-Instruct"
QWEN = "Qwen/Qwen2.5-7B-Instruct"
NC = "acme/nc-tuned"


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


@pytest.fixture
def repo(tmp_path):
    write(tmp_path, "train.py", f'''
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import hf_hub_download, snapshot_download
model = AutoModelForCausalLM.from_pretrained("{FANAR}", torch_dtype="auto")
tok = AutoTokenizer.from_pretrained(pretrained_model_name_or_path='{QWEN}')
cfg = hf_hub_download(
    repo_id="acme/Llama-3.1-8B-tuned",
    filename="config.json",
)
snapshot_download("acme/snap-model")
local = AutoModelForCausalLM.from_pretrained("./checkpoints/run1")
fmt = AutoModelForCausalLM.from_pretrained(f"{{org}}/{{name}}")
bert = AutoModelForCausalLM.from_pretrained("bert-base-uncased")
''')
    write(tmp_path, "configs/run.yaml", f"model: {QWEN}\nbase_model:\n- acme/yaml-base\n- acme/yaml-base-2\n"
                                        "data_path: data/train.json\noutput_dir: outputs/run\n")
    write(tmp_path, "configs/settings.json", json.dumps({"model_name_or_path": "acme/json-model",
                                                         "model_type": "llama", "train_file": "data/x.json"}))
    write(tmp_path, "pyproject.toml", '[tool.eval]\nreward_model = "acme/toml-model"\n')
    write(tmp_path, "nb.ipynb", json.dumps({"cells": [
        {"cell_type": "markdown", "source": ["from_pretrained(\"org/markdown-only\")"]},
        {"cell_type": "code", "source": ["pipe = pipeline('text-generation', model=\"acme/nb-model\")\n"]},
    ]}))
    write(tmp_path, "checkpoints/run1/config.json", "{}")
    write(tmp_path, ".venv/lib/x.py", 'from_pretrained("org/in-venv")')
    write(tmp_path, "node_modules/x/config.json", '{"model": "org/in-node-modules"}')
    write(tmp_path, "notes.md", f'from_pretrained("org/in-markdown")')
    return tmp_path


def test_scan_finds_ids(repo):
    hits = scan(repo)
    ids = set(hits)
    assert {FANAR, QWEN, "acme/Llama-3.1-8B-tuned", "acme/snap-model", "bert-base-uncased", "acme/yaml-base",
            "acme/yaml-base-2", "acme/json-model", "acme/toml-model", "acme/nb-model"} <= ids
    for bad in ("./checkpoints/run1", "checkpoints/run1", "data/train.json", "outputs/run", "org/in-venv",
                "org/in-node-modules", "org/in-markdown", "org/markdown-only", "llama"):
        assert bad not in ids, bad
    assert not any("{" in i for i in ids)
    assert hits[FANAR].places == ["train.py:4"]
    assert "configs/run.yaml:1" in hits[QWEN].places
    assert "train.py:5" in hits[QWEN].places
    assert hits["acme/Llama-3.1-8B-tuned"].places == ["train.py:7"]


def test_scan_single_file(repo):
    assert set(scan(repo / "configs" / "run.yaml")) == {QWEN, "acme/yaml-base", "acme/yaml-base-2"}


def test_check_exit_1_on_block(repo, fake_api, capsys):
    write(repo, "serve.py", f'pipe = pipeline("text-generation", model="{NC}")\n')
    code = cli.main(["check", str(repo)])
    out = capsys.readouterr().out
    assert code == 1
    assert "| Model | Decision | Why | Verdict | Declared license | Upstream terms | Found in |" in out
    assert (f"| {NC} | BLOCK | Non-commercial terms from acme/nc-base (CC BY-NC). | CLOUDED | apache-2.0 | "
            "cc-by-nc-4.0 via acme/nc-base (depth 1) | serve.py:1 |") in out
    assert f"| {FANAR} | CONDITIONS | 2 obligations to meet before shipping. | CLOUDED |" in out
    assert f"| {QWEN} | ALLOW | Nothing restricted found upstream. | NO LIENS FOUND |" in out
    rows = [l for l in out.splitlines() if l.startswith("| ") and "---" not in l][1:]
    assert rows[0].startswith(f"| {NC} | BLOCK")  # BLOCK rows first
    assert "Result: fail. At least one model is BLOCK for commercial use." in out
    assert "violation" not in out.lower()
    assert set(fake_api.uses) == {"commercial"}


def test_conditions_only_passes_without_strict(tmp_path, fake_api, capsys):
    # The case a judge hit: Fanar is CLOUDED but only CONDITIONS, so CI must not fail on it by default.
    write(tmp_path, "a.py", f'from_pretrained("{FANAR}")\nfrom_pretrained("{QWEN}")')
    assert cli.main(["check", str(tmp_path)]) == 0
    assert "Result: pass with conditions." in capsys.readouterr().out
    assert cli.main(["check", str(tmp_path), "--strict"]) == 2


def test_unknown_is_conditions_and_not_on_hub_is_na(tmp_path, fake_api, capsys):
    write(tmp_path, "a.py", 'from_pretrained("acme/no-license")\nfrom_pretrained("nobody/nothing")')
    assert cli.main(["check", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "| acme/no-license | CONDITIONS |" in out
    assert "| nobody/nothing | N/A | No such public model. |" in out
    assert cli.main(["check", str(tmp_path), "--strict"]) == 2
    write(tmp_path, "a.py", 'from_pretrained("nobody/nothing")')
    assert cli.main(["check", str(tmp_path), "--strict"]) == 0


def test_block_wins_over_conditions(tmp_path, fake_api):
    write(tmp_path, "a.py", f'from_pretrained("{FANAR}")\nfrom_pretrained("{NC}")')
    assert cli.main(["check", str(tmp_path), "--strict"]) == 1


def test_use_noncommercial(tmp_path, fake_api, capsys, monkeypatch):
    write(tmp_path, "a.py", f'from_pretrained("{NC}")')
    assert cli.main(["check", str(tmp_path), "--use", "noncommercial"]) == 0
    assert "noncommercial use" in capsys.readouterr().out
    assert fake_api.uses[-1] == "noncommercial"
    monkeypatch.setenv("FINEPRINT_USE", "noncommercial")
    assert cli.main(["check", str(tmp_path)]) == 0
    assert cli.main(["check", str(tmp_path), "--use", "commercial"]) == 1
    monkeypatch.setenv("FINEPRINT_USE", "resale")
    assert cli.main(["check", str(tmp_path)]) == 64


def test_bad_use_flag(tmp_path):
    with pytest.raises(SystemExit) as e:
        cli.main(["check", str(tmp_path), "--use", "resale"])
    assert e.value.code == 64


def test_allow_env_skips_block(tmp_path, fake_api, monkeypatch, capsys):
    write(tmp_path, "a.py", f'from_pretrained("{NC}")')
    monkeypatch.setenv("FINEPRINT_ALLOW", NC)
    assert cli.main(["check", str(tmp_path)]) == 0
    assert "BLOCK (allowed)" in capsys.readouterr().out


def test_old_api_without_decision(tmp_path, fake_api):
    fake_api.with_decision = False  # CLOUDED alone maps to CONDITIONS, never BLOCK
    write(tmp_path, "a.py", f'from_pretrained("{FANAR}")')
    assert cli.main(["check", str(tmp_path)]) == 0
    assert cli.main(["check", str(tmp_path), "--strict"]) == 2


def test_check_unreachable_exit_3(tmp_path, fake_api, capsys):
    fake_api.down = True
    write(tmp_path, "a.py", f'from_pretrained("{FANAR}")')
    assert cli.main(["check", str(tmp_path)]) == 3
    assert "not reachable" in capsys.readouterr().out


def test_fail_open_default_warns_on_stderr(tmp_path, fake_api, capsys):
    fake_api.down = True
    write(tmp_path, "a.py", f'from_pretrained("{FANAR}")')
    assert cli.main(["check", str(tmp_path)]) == 3
    cap = capsys.readouterr()
    assert "WARNING: 1 of 1 models were not checked" in cap.err and "--fail-closed" in cap.err
    assert "Failing open (exit 3)" in cap.out


def test_fail_closed_flag_and_env(tmp_path, fake_api, capsys, monkeypatch):
    fake_api.down = True
    write(tmp_path, "a.py", f'from_pretrained("{FANAR}")')
    assert cli.main(["check", str(tmp_path), "--fail-closed"]) == 1
    assert "Result: fail (fail-closed). 1 model could not be checked" in capsys.readouterr().out
    assert cli.main(["report", QWEN, "--fail-closed"]) == 1
    assert cli.main(["report", QWEN]) == 3
    monkeypatch.setenv("FINEPRINT_FAIL_CLOSED", "1")
    assert cli.main(["check", str(tmp_path)]) == 1
    monkeypatch.setenv("FINEPRINT_ALLOW", FANAR)
    assert cli.main(["check", str(tmp_path)]) == 0


def test_fail_closed_with_partial_outage(tmp_path, fake_api, monkeypatch):
    # One model answers, one fails: fail-open passes with a warning, fail-closed fails.
    write(tmp_path, "a.py", f'from_pretrained("{QWEN}")\nfrom_pretrained("{FANAR}")')
    real = fake_api.handler

    def flaky(request):
        if FANAR in request.url.path:
            raise httpx.ConnectError("refused", request=request)
        return real(request)

    fake_api.api._http._transport = httpx.MockTransport(flaky)
    assert cli.main(["check", str(tmp_path)]) == 0
    assert cli.main(["check", str(tmp_path), "--fail-closed"]) == 1


def test_check_no_models(tmp_path, fake_api, capsys):
    write(tmp_path, "a.py", "print('hi')")
    assert cli.main(["check", str(tmp_path)]) == 0
    assert "No Hugging Face model ids found" in capsys.readouterr().out


def test_check_json(repo, fake_api, capsys):
    write(repo, "serve.py", f'from_pretrained("{NC}")')
    code = cli.main(["check", str(repo), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    by_id = {d["model"]: d for d in data}
    assert by_id[NC]["decision"] == "BLOCK"
    assert by_id[FANAR]["decision"] == "CONDITIONS"
    assert by_id[FANAR]["found_in"] == ["train.py:4"]


def test_report_command(fake_api, capsys):
    code = cli.main(["report", f"https://huggingface.co/{FANAR}/tree/main"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("Decision for commercial use: CONDITIONS. 2 obligations to meet before shipping.")
    assert f"{FANAR}: CLOUDED" in out
    assert "[gemma-3.1-4]" in out
    assert "--fine-tune of--> google/gemma-3-27b-pt [gemma]" in out
    assert fake_api.calls[-1] == f"/api/report/{FANAR}"
    assert cli.main(["report", NC]) == 1
    assert cli.main(["report", NC, "--use", "noncommercial"]) == 0
    assert cli.main(["report", FANAR, "--strict"]) == 2


def test_report_json_and_bad_id(fake_api, capsys):
    assert cli.main(["report", QWEN, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "NO LIENS FOUND"
    assert cli.main(["report", "not a model id!"]) == 64


def test_usage_error_is_not_exit_2():
    with pytest.raises(SystemExit) as e:
        cli.main(["nonsense"])
    assert e.value.code == 64


def test_normalize_model_id():
    n = client.normalize_model_id
    assert n(" QCRI/Fanar-2-27B-Instruct ") == FANAR
    assert n("https://huggingface.co/QCRI/Fanar-2-27B-Instruct/blob/main/README.md") == FANAR
    assert n("hf.co/gpt2") == "gpt2"
    for bad in ("", "a b/c", "../etc/passwd", "org/na me"):
        with pytest.raises(ValueError):
            n(bad)


REJECT_LLAMA = {"id": "r-1", "scope": "license", "target": "llama3.1", "effect": "reject", "use": "any",
                "note": "Llama is off limits here.", "conditions": "", "by": "legal", "at": "2026-10-18"}


def test_check_ruleset_flag_and_env(tmp_path, fake_api, capsys, monkeypatch):
    write(tmp_path, "a.py", 'from_pretrained("acme/Llama-3.1-8B-tuned")\n')
    fake_api.rulings["my-team"] = [REJECT_LLAMA]
    assert cli.main(["check", str(tmp_path)]) == 0
    assert fake_api.rulesets[-1] is None
    assert cli.main(["check", str(tmp_path), "--ruleset", "my-team"]) == 1
    out = capsys.readouterr().out
    assert "commercial use, org rulings my-team" in out
    assert "Org rulings applied:" in out and "CONDITIONS -> BLOCK" in out and "Llama is off limits here." in out
    monkeypatch.setenv("FINEPRINT_RULESET", "my-team")
    assert cli.main(["check", str(tmp_path)]) == 1
    assert cli.main(["report", "acme/Llama-3.1-8B-tuned"]) == 1
    monkeypatch.setenv("FINEPRINT_RULESET", "Not Valid")
    assert cli.main(["check", str(tmp_path)]) == 64
