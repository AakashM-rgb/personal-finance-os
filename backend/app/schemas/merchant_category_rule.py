"""Merchant category rule request/response schemas.

`merchant` on the create request is free text - a raw narration or a
manually-typed name. app.services.merchant_rule_service always re-
normalizes it through the one shared
app.services.merchant_normalization.normalize_merchant algorithm before
anything is stored, so `merchant_key` on the response is always the
canonical form, never whatever the caller happened to type. `category_id`
is the only field `MerchantCategoryRuleUpdate` accepts - merchant_key is a
rule's identity, not something a client repoints in place.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MerchantCategoryRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant: str = Field(min_length=1, max_length=500)
    category_id: UUID


class MerchantCategoryRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID


class MerchantCategoryRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_key: str
    category_id: UUID
    category_name: str
    category_icon: str
    category_color: str
    created_at: datetime
    updated_at: datetime
