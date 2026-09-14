"""Category request/response schemas."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    icon: str = Field(min_length=1, max_length=50)
    color: str
    budget_minor: int | None = Field(default=None, ge=0)
    parent_id: UUID | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not _HEX_COLOR_RE.match(value):
            raise ValueError("color must be a hex code like #F59E0B")
        return value.upper()


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = None
    budget_minor: int | None = Field(default=None, ge=0)
    parent_id: UUID | None = None
    clear_parent: bool = False  # explicit flag - parent_id=None alone means "no change"

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is not None and not _HEX_COLOR_RE.match(value):
            raise ValueError("color must be a hex code like #F59E0B")
        return value.upper() if value else value


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    icon: str
    color: str
    budget_minor: int | None
    parent_id: UUID | None
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
