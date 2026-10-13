"""Base model shared by every feature's request and response models."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Uses snake_case in Python but camelCase in JSON, to match NestJS."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
