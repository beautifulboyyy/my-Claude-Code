"""Shared JSON-compatible typing primitives for Agent Flow core models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeAlias

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | Mapping[str, "JsonValue"] | Sequence["JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

