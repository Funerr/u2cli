from __future__ import annotations

import pytest

from u2cli.element.selector import bounds_to_list, selector_from_kwargs
from u2cli.errors import U2CliError


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
