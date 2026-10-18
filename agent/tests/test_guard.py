import importlib
import io
import sys
import types

import httpx
import pytest

import fineprint
from fineprint import client

hub = pytest.importorskip("huggingface_hub")
import huggingface_hub.file_download as hub_fd  # noqa: E402
import huggingface_hub._snapshot_download as hub_sd  # noqa: E402

FANAR = "QCRI/Fanar-2-27B-Instruct"
QWEN = "Qwen/Qwen2.5-7B-Instruct"
LLAMA = "acme/Llama-3.1-8B-tuned"
NC = "acme/nc-tuned"


@pytest.fixture
def fake_hub(monkeypatch):
    """Replace the real download functions with recorders before the guard wraps them."""
    calls = []

    def hf_hub_download(repo_id, filename=None, **kw):
        calls.append(("file", repo_id, filename, kw.get("repo_type")))
        return f"/cache/{repo_id}/{filename}"

    def snapshot_download(repo_id, **kw):
        calls.append(("snapshot", repo_id, None, kw.get("repo_type")))
        return f"/cache/{repo_id}"

    for mod in (hub, hub_fd):
        monkeypatch.setattr(mod, "hf_hub_download", hf_hub_download, raising=False)
    for mod in (hub, hub_sd):
        monkeypatch.setattr(mod, "snapshot_download", snapshot_download, raising=False)
    # A user module that ran `from huggingface_hub import hf_hub_download` before guard().
    userlib = types.ModuleType("fineprint_test_userlib")
    userlib.hf_hub_download = hf_hub_download
    monkeypatch.setitem(sys.modules, "fineprint_test_userlib", userlib)
    return calls


def test_warn_prints_decision_why_and_obligations(fake_api, fake_hub):
    err = io.StringIO()
    fineprint.guard("warn", stream=err)
    assert hub.hf_hub_download(FANAR, "config.json") == f"/cache/{FANAR}/config.json"
    out = err.getvalue()
    assert out.startswith(f"fineprint: {FANAR} for commercial use: CONDITIONS. 2 obligations to meet before shipping.")
    assert "verdict CLOUDED" in out and "gemma via google/gemma-3-27b-pt" in out
    assert 'Ship a "Notice" file' in out
    assert fake_hub == [("file", FANAR, "config.json", None)]


def test_warn_mode_never_raises_on_block(fake_api, fake_hub):
    err = io.StringIO()
    fineprint.guard("warn", stream=err)
    hub.hf_hub_download(NC, "config.json")
    assert f"{NC} for commercial use: BLOCK. Non-commercial terms from acme/nc-base (CC BY-NC)." in err.getvalue()
    assert len(fake_hub) == 1


def test_warn_is_quiet_for_allow(fake_api, fake_hub):
    err = io.StringIO()
    fineprint.guard("warn", stream=err)
    hub.snapshot_download(repo_id=QWEN)
    assert err.getvalue() == ""
    assert fake_hub == [("snapshot", QWEN, None, None)]


def test_block_raises_on_block_decision(fake_api, fake_hub):
    fineprint.guard("block", stream=io.StringIO())
    with pytest.raises(fineprint.FinePrintBlocked) as exc:
        hub.hf_hub_download(repo_id=NC, filename="model.safetensors")
    assert exc.value.model_id == NC
    assert exc.value.decision == "BLOCK"
    assert exc.value.why == "Non-commercial terms from acme/nc-base (CC BY-NC)."
    msg = str(exc.value)
    assert msg.startswith(f"FinePrint blocked the download of {NC} for commercial use: Non-commercial terms")
    assert "Non-commercial use only." in msg and "FINEPRINT_ALLOW" in msg and "FINEPRINT_USE=noncommercial" in msg
    assert fake_hub == []
    with pytest.raises(fineprint.FinePrintBlocked):
        hub.snapshot_download(NC)  # from cache
    assert fake_api.report_calls() == 1


def test_block_lets_clouded_conditions_through(fake_api, fake_hub):
    # CLOUDED alone is CONDITIONS, not BLOCK.
    err = io.StringIO()
    fineprint.guard("block", stream=err)
    hub.hf_hub_download(FANAR, "config.json")
    hub.hf_hub_download(LLAMA, "config.json")
    out = err.getvalue()
    assert f"{FANAR} for commercial use: CONDITIONS" in out
    assert f"{LLAMA} for commercial use: CONDITIONS" in out and 'Start the model name with "Llama"' in out
    assert len(fake_hub) == 2


def test_block_is_not_an_exception_subclass():
    # library code that catches Exception must not swallow it
    assert not issubclass(fineprint.FinePrintBlocked, Exception)


def test_unknown_warns_and_not_on_hub_is_quiet(fake_api, fake_hub):
    err = io.StringIO()
    fineprint.guard("block", stream=err)
    hub.hf_hub_download("acme/no-license", "x.bin")
    assert "acme/no-license for commercial use: CONDITIONS. Lineage or license unknown" in err.getvalue()
    before = err.getvalue()
    hub.hf_hub_download("nobody/nothing", "x.bin")  # N/A: the Hub will answer for itself
    assert err.getvalue() == before
    assert len(fake_hub) == 2


def test_noncommercial_use(fake_api, fake_hub, monkeypatch):
    err = io.StringIO()
    fineprint.guard("block", use="noncommercial", stream=err)
    hub.hf_hub_download(NC, "config.json")
    assert f"{NC} for noncommercial use: CONDITIONS" in err.getvalue()
    assert fake_api.uses == ["noncommercial"]
    fineprint.unguard()
    monkeypatch.setenv("FINEPRINT_USE", "noncommercial")
    fineprint.guard("block", stream=io.StringIO())
    hub.hf_hub_download(NC, "config.json")
    monkeypatch.setenv("FINEPRINT_USE", "commercial")  # read at check time, cached per use
    with pytest.raises(fineprint.FinePrintBlocked):
        hub.hf_hub_download(NC, "config.json")
    assert len(fake_hub) == 2


def test_bad_use():
    with pytest.raises(ValueError):
        fineprint.guard("block", use="resale")


def test_allow_list_and_env(fake_api, fake_hub, monkeypatch):
    fineprint.guard("block", allow=[NC], stream=io.StringIO())
    hub.hf_hub_download(NC, "config.json")
    fineprint.unguard()
    monkeypatch.setenv("FINEPRINT_ALLOW", f"other/x, {NC}")
    fineprint.guard("block", stream=io.StringIO())
    hub.hf_hub_download(NC, "config.json")
    assert len(fake_hub) == 2


def test_old_api_without_decision_never_blocks(fake_api, fake_hub):
    fake_api.with_decision = False
    err = io.StringIO()
    fineprint.guard("block", stream=err)
    hub.hf_hub_download(NC, "config.json")
    assert "CONDITIONS" in err.getvalue()
    assert len(fake_hub) == 1


def test_fail_open_when_api_unreachable(fake_api, fake_hub):
    fake_api.down = True
    err = io.StringIO()
    fineprint.guard("block", stream=err)
    hub.hf_hub_download(FANAR, "config.json")
    hub.hf_hub_download(FANAR, "tokenizer.json")
    lines = err.getvalue().strip().splitlines()
    assert len(lines) == 1
    assert "could not check" in lines[0] and "unchecked (fail-open)" in lines[0]
    assert len(fake_hub) == 2


def test_fail_open_on_real_closed_port(fake_hub, monkeypatch):
    monkeypatch.setenv("FINEPRINT_API", "http://127.0.0.1:9")
    client.set_api(None)
    err = io.StringIO()
    fineprint.guard("block", stream=err)
    hub.hf_hub_download(FANAR, "config.json")
    assert "not reachable" in err.getvalue()
    assert len(fake_hub) == 1


def test_checks_once_per_model(fake_api, fake_hub):
    fineprint.guard("warn", stream=io.StringIO())
    for f in ("a", "b", "c"):
        hub.hf_hub_download(QWEN, f)
    assert fake_api.report_calls() == 1


def test_datasets_and_spaces_are_not_checked(fake_api, fake_hub):
    fineprint.guard("block", stream=io.StringIO())
    hub.hf_hub_download(FANAR, "data.parquet", repo_type="dataset")
    hub.snapshot_download(FANAR, repo_type="space")
    assert fake_api.report_calls() == 0
    assert len(fake_hub) == 2


def test_patches_copies_held_by_other_modules(fake_api, fake_hub):
    fineprint.guard("block", stream=io.StringIO())
    userlib = sys.modules["fineprint_test_userlib"]
    with pytest.raises(fineprint.FinePrintBlocked):
        userlib.hf_hub_download(NC, "config.json")
    with pytest.raises(fineprint.FinePrintBlocked):
        hub_fd.hf_hub_download(NC, "config.json")


def test_unguard_restores_originals(fake_api, fake_hub):
    original = hub_fd.hf_hub_download
    fineprint.guard("block", stream=io.StringIO())
    assert hub_fd.hf_hub_download is not original
    fineprint.unguard()
    assert hub_fd.hf_hub_download is original
    assert sys.modules["fineprint_test_userlib"].hf_hub_download is original
    hub.hf_hub_download(FANAR, "config.json")
    assert fake_api.report_calls() == 0


def test_guard_twice_does_not_double_wrap(fake_api, fake_hub):
    fineprint.guard("warn", stream=io.StringIO())
    fineprint.guard("block", stream=io.StringIO())
    with pytest.raises(fineprint.FinePrintBlocked):
        hub.hf_hub_download(NC, "config.json")
    fineprint.guard("off")
    hub.hf_hub_download(NC, "config.json")
    assert fineprint.status() == "off"
    assert len(fake_hub) == 1


def test_bad_mode():
    with pytest.raises(ValueError):
        fineprint.guard("loud")


def test_mode_from_env(fake_api, fake_hub, monkeypatch):
    monkeypatch.setenv("FINEPRINT_GUARD", "block")
    fineprint.guard(stream=io.StringIO())
    assert fineprint.status() == "block"


@pytest.mark.parametrize("env,expected", [("block", "block"), ("warn", "warn"), ("off", "off"), (None, "warn")])
def test_autoguard(fake_api, fake_hub, monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("FINEPRINT_GUARD", raising=False)
    else:
        monkeypatch.setenv("FINEPRINT_GUARD", env)
    import fineprint.autoguard as ag
    importlib.reload(ag)
    assert fineprint.status() == expected


def test_transformers_from_pretrained_is_blocked(fake_api):
    transformers = pytest.importorskip("transformers")
    fineprint.guard("block", stream=io.StringIO())
    # Blocked before any network call, so this needs no Hub access.
    with pytest.raises(fineprint.FinePrintBlocked):
        transformers.AutoConfig.from_pretrained(NC)
    with pytest.raises(fineprint.FinePrintBlocked):
        transformers.AutoTokenizer.from_pretrained(NC)


def test_unreachable_api_error_type():
    api = client.Api(base="http://x.test", transport=httpx.MockTransport(
        lambda r: (_ for _ in ()).throw(httpx.ConnectTimeout("t", request=r))))
    with pytest.raises(client.ApiUnavailable):
        api.report(FANAR)


def test_fail_open_warning_is_clear(fake_api, fake_hub):
    fake_api.down = True
    err = io.StringIO()
    fineprint.guard("block", stream=err)
    hub.hf_hub_download(NC, "config.json")
    out = err.getvalue()
    assert "WARNING" in out and "unchecked (fail-open)" in out and "FINEPRINT_FAIL_CLOSED=1" in out
    assert len(fake_hub) == 1


@pytest.mark.parametrize("mode", ["block", "warn"])
def test_fail_closed_raises_when_api_down(fake_api, fake_hub, mode):
    fake_api.down = True
    fineprint.guard(mode, fail_closed=True, stream=io.StringIO())
    with pytest.raises(fineprint.FinePrintBlocked) as exc:
        hub.hf_hub_download(QWEN, "config.json")
    assert exc.value.decision == "BLOCK"
    assert "could not check" in exc.value.why and "fail-closed" in exc.value.why
    assert "Verdict:" not in str(exc.value)
    assert fake_hub == []
    # not cached: once the API is back, the same model downloads
    fake_api.down = False
    hub.hf_hub_download(QWEN, "config.json")
    assert len(fake_hub) == 1


def test_fail_closed_from_env_and_allow_list(fake_api, fake_hub, monkeypatch):
    fake_api.down = True
    monkeypatch.setenv("FINEPRINT_FAIL_CLOSED", "1")
    fineprint.guard("block", allow=[FANAR], stream=io.StringIO())
    with pytest.raises(fineprint.FinePrintBlocked):
        hub.snapshot_download(QWEN)
    hub.hf_hub_download(FANAR, "config.json")  # allowed models pass even when unchecked
    assert len(fake_hub) == 1
    fineprint.unguard()
    fineprint.guard("block", fail_closed=False, stream=io.StringIO())  # argument beats env
    hub.snapshot_download(QWEN)
    assert len(fake_hub) == 2


def test_ruleset_from_env_blocks_and_caches_per_ruleset(fake_api, fake_hub, monkeypatch):
    fake_api.rulings["my-team"] = [{"id": "r-1", "scope": "license", "target": "llama3.1", "effect": "reject",
                                    "use": "any", "note": "Llama is off limits here.", "conditions": "",
                                    "by": "legal", "at": "2026-10-18"}]
    fineprint.guard("block", stream=io.StringIO())
    hub.hf_hub_download(LLAMA, "config.json")  # CONDITIONS without org rulings
    monkeypatch.setenv("FINEPRINT_RULESET", "my-team")
    with pytest.raises(fineprint.FinePrintBlocked) as e:
        hub.hf_hub_download(LLAMA, "config.json")
    assert e.value.why == "Llama is off limits here."
    assert "Org rulings (my-team): CONDITIONS -> BLOCK" in str(e.value)
    assert fake_api.rulesets == [None, "my-team"]
    fineprint.unguard()
    with pytest.raises(ValueError):
        fineprint.guard("block", ruleset="Not Valid")
