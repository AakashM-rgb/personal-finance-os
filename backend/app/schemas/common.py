"""Shared response envelope used by every endpoint."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    field_errors: dict[str, str] | None = None


class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    error: ErrorDetail | None = None
    meta: dict | None = None
