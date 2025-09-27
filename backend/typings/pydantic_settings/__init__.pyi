from typing import Any, TypedDict

class SettingsConfigDict(TypedDict, total=False):
    env_file: str | None
    case_sensitive: bool
    extra: str
    env_prefix: str
    env_nested_delimiter: str
    env_file_encoding: str


class BaseSettings:
    model_config: SettingsConfigDict

    def __init__(self, **data: Any) -> None: ...

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...
