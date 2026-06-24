from __future__ import annotations

import json
from pathlib import Path

import pytest

import androidtestclii.cli as cli_module
from androidtestclii.context import CommandContext
from androidtestclii.element import action as element_action
from androidtestclii.element import query as element_query
from androidtestclii.element.selector import selector_from_kwargs
from androidtestclii.errors import ErrorCode, U2CliError
from androidtestclii.screen import dump as screen_dump


def ctx() -> CommandContext:
    return CommandContext.start(serial="emulator-5554", timeout_ms=1000)


def run_main(args: list[str], capsys) -> tuple[int, dict]:
    try:
        cli_module.main(args)
    except SystemExit as exc:
        code = int(exc.code or 0)
    else:
        code = 0
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


def fixture_xml() -> str:
    return Path("tests/fixtures/raw_ui_dump_compact_refs.xml").read_text(encoding="utf-8")


def test_screen_dump_compact_writes_artifacts_without_inline_raw(
    fake_device,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANDROIDTESTCLII_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    fake_device.dump_hierarchy = fixture_xml

    data = screen_dump.dump(ctx(), compact=True)

    assert data["snapshotId"]
    assert "xml" not in data
    raw_path = Path(data["rawArtifactPath"])
    compact_path = Path(data["compactArtifactPath"])
    ref_map_path = Path(data["refMapPath"])
    assert raw_path.exists()
    assert compact_path.exists()
    assert ref_map_path.exists()
    assert raw_path.read_text(encoding="utf-8").startswith("<hierarchy")

    compact_payload = json.loads(compact_path.read_text(encoding="utf-8"))
    assert compact_payload["snapshotId"] == data["snapshotId"]
    assert "xml" not in compact_payload

    ref_map = json.loads(ref_map_path.read_text(encoding="utf-8"))
    assert ref_map["snapshotId"] == data["snapshotId"]
    assert ref_map["rawArtifactPath"] == data["rawArtifactPath"]
    assert ref_map["compactArtifactPath"] == data["compactArtifactPath"]
    assert "@e0" in ref_map["refs"]
    assert ref_map["refs"]["@e0"]["rawNodePath"]


def test_ref_target_click_set_text_and_wait_use_snapshot_ref_map(
    fake_device,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANDROIDTESTCLII_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    data = screen_dump.dump(ctx(), compact=True)
    target = {"ref": "@e0", "snapshotId": data["snapshotId"]}

    clicked = element_action.click(ctx(), target)
    assert clicked["via"] == "bounds"
    assert fake_device.taps[-1] == (380, 1260)

    typed = element_action.set_text(ctx(), target, "qa@example.com")
    assert typed["via"] == "bounds"
    assert fake_device.sent_text[-1] == "qa@example.com"

    waited = element_query.wait(ctx(), target)
    assert waited["matched"] is True
    assert waited["selector"]["text"] == "Login"

    selector_click = element_action.click(ctx(), selector_from_kwargs(text="Login"))
    assert selector_click["clicked"] is True


def test_missing_ref_error_includes_candidates_and_raw_artifact(
    fake_device,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANDROIDTESTCLII_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    data = screen_dump.dump(ctx(), compact=True)

    with pytest.raises(U2CliError) as error:
        element_action.click(ctx(), {"ref": "@e99", "snapshotId": data["snapshotId"]})

    assert error.value.code == ErrorCode.SNAPSHOT_REF_NOT_FOUND
    assert error.value.details["snapshotId"] == data["snapshotId"]
    assert error.value.details["ref"] == "@e99"
    assert "@e0" in error.value.details["candidateRefs"]
    assert error.value.details["rawArtifactPath"] == data["rawArtifactPath"]


def test_element_cli_accepts_json_ref_target(fake_device, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("ANDROIDTESTCLII_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    data = screen_dump.dump(ctx(), compact=True)
    target = {"ref": "@e0", "snapshotId": data["snapshotId"]}

    code, payload = run_main(
        [
            "--serial",
            "emulator-5554",
            "element",
            "click",
            "--target",
            json.dumps(target),
        ],
        capsys,
    )

    assert code == 0
    assert payload["data"]["via"] == "bounds"
    assert fake_device.taps[-1] == (380, 1260)
