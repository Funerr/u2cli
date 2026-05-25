from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from u2cli.errors import ErrorCode, U2CliError


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


BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


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
