import pytest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("builder", Path(__file__).parent.parent / "scripts" / "midistomp_builder.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_refuses_other_files(tmp_path):
    f = tmp_path / "x.exe"
    f.write_bytes(b"not zoom")
    assert builder.run([str(f)]) == 1
    assert not (tmp_path / builder.OUT_NAME).exists()
    assert not (tmp_path / builder.OUT_NAME_OC).exists()


def test_patch_files_exist():
    assert all((builder.ROOT / "patches" / f"{p}.yaml").exists() for p in builder.PATCHES)


def test_release_sections_do_not_overlap():
    from zoomms import patcher
    spans = sorted((s["addr"], s["addr"] + len(bytes.fromhex("".join(s["data"].split()))), p)
                   for p in builder.PATCHES
                   for s in patcher.load(builder.ROOT / "patches" / f"{p}.yaml").get("section", []))
    for (_, end, a), (start, _, b) in zip(spans, spans[1:]):
        assert end <= start, f"{a} and {b} overlap at 0x{start:08X}"


def test_refuses_other_mac_apps(tmp_path):
    app = tmp_path / "x.app"
    exe = app / "Contents" / "MacOS" / "EFX Updater"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"not zoom")
    assert builder.run([str(app)]) == 1
    assert not (tmp_path / builder.OUT_NAME_MAC).exists()
    assert not (tmp_path / builder.OUT_NAME_OC_MAC).exists()


def test_ask_path_reads_a_dragged_mac_path(monkeypatch):
    # Terminal pastes a dragged app shell-escaped, with a trailing space
    monkeypatch.setattr("builtins.input", lambda: r"/Users/me/Downloads/ZOOM\ MS-70CDR\ v2.10\ Updater.app ")
    assert builder.ask_path() == ["/Users/me/Downloads/ZOOM MS-70CDR v2.10 Updater.app"]
    monkeypatch.setattr("builtins.input", lambda: "")
    assert builder.ask_path() == []


def test_identity_tag_follows_the_version():
    assert builder.identity_tag("MIDISTOMP V2.0.1") == "M201"
    assert builder.identity_tag("MIDISTOMP V2.1.0") == "M210"
    assert builder.identity_tag("MIDISTOMP V2.0.4.1") == "M204"
    with pytest.raises(ValueError):
        builder.identity_tag("MIDISTOMP V2.1")


def test_feature_dependencies_json_matches_release():
    import json
    d = json.loads((builder.ROOT / "docs" / "dev" / "feature-dependencies.json").read_text())
    assert d["order"] == builder.PATCHES == list(d["patches"])
    for p, v in d["patches"].items():   # every need is applied earlier
        assert all(d["order"].index(n) < d["order"].index(p) for n in v["needs"] + v["optional"]), p


def stock_133():
    d = bytearray(b"\xff" * 0x3000)
    d[0x2C00] = 0x61
    return d


def test_set_pedal_model_changes_only_the_model_byte():
    from zoomms import cli
    for pedal, want in (("ms50g", 0x58), ("ms60b", 0x5F), ("ms70cdr", 0x61)):
        d = stock_133()
        cli.set_pedal_model(d, pedal)
        expected = stock_133()
        expected[0x2C00] = want
        assert d == expected


def test_set_pedal_model_refuses_a_part_without_a_model_byte():
    import pytest
    from zoomms import cli
    with pytest.raises(ValueError):
        cli.set_pedal_model(bytearray(b"\xff" * 0x3000), "ms50g")
    with pytest.raises(ValueError):
        cli.set_pedal_model(bytearray(16), "ms50g")


def test_builder_refuses_an_unknown_pedal(tmp_path):
    f = tmp_path / "x.exe"
    f.write_bytes(b"not zoom")
    assert builder.run([str(f), "--pedal", "ms99"]) == 1


def test_builder_passes_the_pedal_on(monkeypatch):
    seen = []
    monkeypatch.setattr(builder.cli, "main", lambda argv: seen.extend(argv) or 0)
    assert builder.build(Path("x.app"), Path("y.app"), True, pedal="ms50g") == 0
    assert seen[seen.index("--pedal") + 1] == "ms50g"


def test_no_pedal_keeps_the_release_build_as_it_was(monkeypatch):
    seen = []
    monkeypatch.setattr(builder.cli, "main", lambda argv: seen.extend(argv) or 0)
    builder.build(Path("x.app"), Path("y.app"), True)
    assert "--pedal" not in seen


def test_build_mac_from_exe_refuses_pedal(tmp_path, capsys):
    from zoomms import cli
    res = tmp_path / "x.app" / "Contents" / "Resources"
    res.mkdir(parents=True)
    (res / "Main.bin").write_bytes(b"m")
    (res / "Preset.bin").write_bytes(b"p")
    argv = ["build-mac", str(tmp_path / "x.app"), "--from-exe", "a.exe", "--pedal", "ms50g",
            "--out", str(tmp_path / "o.zip")]
    assert cli.main(argv) == 1
    assert "--pedal" in capsys.readouterr().err
