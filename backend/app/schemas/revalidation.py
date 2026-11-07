"""Typed envelope shared with the frontend revalidation endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import APIModel


class RevalidationEvent(APIModel):
    entity: Literal[
        "homepage",
        "shell",
        "product",
        "category",
        "review",
        "flash_sale",
        "shipping",
    ]
    event: Literal["created", "updated", "deleted", "published"]
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    locale: Literal["bn", "en"] | None = None

    @field_validator("slug")
    @classmethod
    def safe_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized.replace("_", "-").replace("-", "").isalnum():
            raise ValueError("slug contains unsupported characters")
        return normalized

    @model_validator(mode="after")
    def validate_entity_requirements(self) -> RevalidationEvent:
        if self.entity in {"product", "category", "review"} and self.slug is None:
            raise ValueError(f"{self.entity} revalidation requires a slug")
        return self
