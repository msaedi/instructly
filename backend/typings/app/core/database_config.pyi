from typing import Literal

DatabaseEnvironment = Literal["int", "stg", "prod"]


class DatabaseConfig:
    def __init__(self) -> None: ...

    def get_database_url(self) -> str: ...
