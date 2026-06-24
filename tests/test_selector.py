from __future__ import annotations

import pytest

from androidtestclii.element.selector import bounds_to_list, from_target, parse_target_selector, selector_from_kwargs
from androidtestclii.session.store import LastSnapshot, SnapshotRef, update_session
from androidtestclii.errors import U2CliError


def test_selector_aliases_and_payload() -> None:
    selector = selector_from_kwargs(text="登录", resource_id="com.example:id/login")

    assert selector.public_dict() == {"text": "登录", "resourceId": "com.example:id/login"}
    assert selector.u2_payload() == (
        "u2",
        {"text": "登录", "resourceId": "com.example:id/login"},
    )


def test_selector_requires_a_field() -> None:
    with pytest.raises(U2CliError) as exc:
        selector_from_kwargs()

    assert exc.value.code.value == "INVALID_ARGUMENT"


def test_xpath_cannot_mix_with_other_fields() -> None:
    with pytest.raises(U2CliError):
        selector_from_kwargs(text="Login", xpath="//*[@text='Login']")


def test_bounds_parse() -> None:
    assert bounds_to_list("[1,2][3,4]") == [1, 2, 3, 4]
    assert bounds_to_list("bad") is None


def test_parse_target_selector_aliases() -> None:
    assert parse_target_selector("text=登录").public_dict() == {"text": "登录"}
    assert parse_target_selector('id="com.example:id/login"').public_dict() == {
        "resourceId": "com.example:id/login"
    }
    assert parse_target_selector("testid=login").public_dict() == {"resourceId": "login"}
    assert parse_target_selector("desc=Submit").public_dict() == {"description": "Submit"}
    assert parse_target_selector("Login").public_dict() == {"text": "Login"}
    assert from_target("text=Login").public_dict() == {"text": "Login"}


def test_from_target_resolves_snapshot_ref(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANDROIDTESTCLII_SESSION_PATH", str(tmp_path / "session.json"))
    update_session(
        serial="emulator-5554",
        last_snapshot=LastSnapshot(
            capturedAt="2026-05-26T00:00:00.000Z",
            serial="emulator-5554",
            refMap={"@e0": SnapshotRef(selector={"text": "Login"})},
        ),
    )

    assert from_target("@e0").public_dict() == {"text": "Login"}
