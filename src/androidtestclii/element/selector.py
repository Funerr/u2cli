from __future__ import annotations

import re
import shlex
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from androidtestclii.errors import ErrorCode, U2CliError


class Selector(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str | None = None
    text_contains: str | None = Field(default=None, alias="textContains")
    resource_id: str | None = Field(default=None, alias="resourceId")
    description: str | None = None
    description_contains: str | None = Field(default=None, alias="descriptionContains")
    class_name: str | None = Field(default=None, alias="className")
    xpath: str | None = None
    index: int | None = None

    @field_validator("*", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def validate_selector(self) -> "Selector":
        fields = [
            self.text,
            self.text_contains,
            self.resource_id,
            self.description,
            self.description_contains,
            self.class_name,
            self.xpath,
        ]
        if not any(value is not None for value in fields):
            raise ValueError("At least one selector field is required")
        if self.xpath and any(
            value is not None
            for value in [
                self.text,
                self.text_contains,
                self.resource_id,
                self.description,
                self.description_contains,
                self.class_name,
            ]
        ):
            raise ValueError("xpath cannot be combined with non-index selector fields")
        if self.index is not None and self.index < 0:
            raise ValueError("index must be greater than or equal to 0")
        return self

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)

    def u2_payload(self) -> tuple[str, dict[str, Any]]:
        if self.xpath:
            return "xpath", {"xpath": self.xpath, "index": self.index}
        payload: dict[str, Any] = {}
        if self.text is not None:
            payload["text"] = self.text
        if self.text_contains is not None:
            payload["textContains"] = self.text_contains
        if self.resource_id is not None:
            payload["resourceId"] = self.resource_id
        if self.description is not None:
            payload["description"] = self.description
        if self.description_contains is not None:
            payload["descriptionContains"] = self.description_contains
        if self.class_name is not None:
            payload["className"] = self.class_name
        return "u2", payload


def selector_from_kwargs(
    *,
    text: str | None = None,
    text_contains: str | None = None,
    resource_id: str | None = None,
    description: str | None = None,
    description_contains: str | None = None,
    class_name: str | None = None,
    xpath: str | None = None,
    index: int | None = None,
) -> Selector:
    try:
        return Selector(
            text=text,
            textContains=text_contains,
            resourceId=resource_id,
            description=description,
            descriptionContains=description_contains,
            className=class_name,
            xpath=xpath,
            index=index,
        )
    except ValidationError as exc:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "Invalid selector",
            {"errors": exc.errors(include_url=False)},
        ) from exc


TARGET_KEY_ALIASES = {
    "text": "text",
    "text_contains": "text_contains",
    "text-contains": "text_contains",
    "contains": "text_contains",
    "id": "resource_id",
    "resource-id": "resource_id",
    "resourceId": "resource_id",
    "resource_id": "resource_id",
    "rid": "resource_id",
    "testid": "resource_id",
    "test-id": "resource_id",
    "class": "class_name",
    "class-name": "class_name",
    "className": "class_name",
    "class_name": "class_name",
    "description": "description",
    "desc": "description",
    "content-desc": "description",
    "description_contains": "description_contains",
    "description-contains": "description_contains",
    "desc_contains": "description_contains",
    "desc-contains": "description_contains",
    "xpath": "xpath",
}


def parse_target_selector(value: str) -> Selector:
    target = value.strip()
    if not target:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "selector target must not be empty",
            {"target": value},
        )
    if target.startswith("@e"):
        raise U2CliError(
            ErrorCode.SNAPSHOT_REF_NOT_FOUND,
            "Snapshot ref must be resolved from session before selector parsing",
            {"ref": target},
        )
    if "=" not in target:
        return selector_from_kwargs(text=_unquote_target_value(target))
    key, raw = target.split("=", 1)
    field = TARGET_KEY_ALIASES.get(key.strip())
    if field is None:
        raise U2CliError(
            ErrorCode.INVALID_ARGUMENT,
            "Unsupported selector target field",
            {"field": key.strip(), "target": value},
        )
    parsed_value = _unquote_target_value(raw.strip())
    kwargs: dict[str, Any] = {field: parsed_value}
    return selector_from_kwargs(**kwargs)


def from_target(value: str | dict[str, Any]) -> Selector:
    if isinstance(value, dict):
        ref = value.get("ref")
        snapshot_id = value.get("snapshotId") or value.get("snapshot_id")
        if not isinstance(ref, str) or not ref.strip():
            raise U2CliError(
                ErrorCode.INVALID_ARGUMENT,
                "snapshot ref target must include ref",
                {"target": value},
            )
        from androidtestclii.session.store import ref_entry

        entry, _ = ref_entry(ref, snapshot_id=snapshot_id if isinstance(snapshot_id, str) else None)
        selector = selector_from_ref(entry)
        if selector is None:
            raise U2CliError(
                ErrorCode.SNAPSHOT_REF_INVALID,
                "Snapshot ref does not contain a valid selector",
                {"ref": ref if ref.startswith("@") else f"@{ref}", "entry": entry.public_dict()},
            )
        return selector
    target = value.strip()
    if target.startswith("@e"):
        from androidtestclii.session.store import ref_entry

        entry, _ = ref_entry(target)
        selector = selector_from_ref(entry)
        if selector is None:
            raise U2CliError(
                ErrorCode.SNAPSHOT_REF_INVALID,
                "Snapshot ref does not contain a valid selector",
                {"ref": target, "entry": entry.public_dict()},
            )
        return selector
    return parse_target_selector(value)


def selector_from_ref(entry: Any) -> Selector | None:
    raw = getattr(entry, "selector", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    text = raw.get("text") or getattr(entry, "text", None)
    resource_id = raw.get("resourceId") or raw.get("resource_id") or getattr(entry, "resource_id", None)
    description = raw.get("description") or getattr(entry, "content_desc", None) or getattr(entry, "description", None)
    class_name = raw.get("className") or raw.get("class_name") or getattr(entry, "class_name", None)
    try:
        return selector_from_kwargs(
            text=text,
            resource_id=resource_id,
            description=description,
            class_name=class_name,
        )
    except U2CliError:
        return None


def _unquote_target_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        try:
            parts = shlex.split(stripped)
        except ValueError:
            return stripped[1:-1]
        if len(parts) == 1:
            return parts[0]
    return stripped


BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def bounds_to_list(value: str | None) -> list[int] | None:
    if not value:
        return None
    match = BOUNDS_RE.fullmatch(value)
    if not match:
        return None
    return [int(group) for group in match.groups()]


def short_class_name(value: str | None) -> str | None:
    if not value:
        return None
    return value.rsplit(".", 1)[-1]
