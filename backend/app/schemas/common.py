"""Common strict Pydantic contracts."""

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FieldError(APIModel):
    field: str
    code: str
    message: str | None = None


class ErrorBody(APIModel):
    code: str
    message: str
    field_errors: list[FieldError]
    request_id: str | None


class ErrorEnvelope(APIModel):
    error: ErrorBody
