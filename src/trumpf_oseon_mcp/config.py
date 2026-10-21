"""Configuration is read at startup, never during package import."""

import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    api_file: str
    base_url: str
    authorization: str = field(default="", repr=False)
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    user_header: str = field(default="", repr=False)
    terminal_header: str = field(default="", repr=False)
    api_version: str = "2.0"
    allow_writes: bool = False
    timeout: float = 30.0

    def __post_init__(self) -> None:
        url = urlsplit(self.base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError(
                "OSEON_BASE_URL must be an HTTP(S) origin without credentials"
            )
        if not self.api_file:
            raise ValueError("OSEON_API_FILE is required")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("OSEON_TIMEOUT must be a positive finite number")
        if bool(self.username) != bool(self.password):
            raise ValueError("Configure both Basic authentication values or neither")
        if self.authorization and self.username:
            raise ValueError(
                "Configure Authorization or Basic authentication, not both"
            )
        for value in (
            self.authorization,
            self.user_header,
            self.terminal_header,
            self.api_version,
        ):
            if any(ord(c) < 32 or ord(c) > 126 for c in value):
                raise ValueError("Configured HTTP headers must contain printable ASCII")


def get_config() -> Config:
    enabled = os.getenv("OSEON_ALLOW_WRITES", "false").lower()
    if enabled not in {"true", "false"}:
        raise ValueError("OSEON_ALLOW_WRITES must be true or false")
    return Config(
        api_file=os.getenv("OSEON_API_FILE", ""),
        base_url=os.getenv("OSEON_BASE_URL", ""),
        authorization=os.getenv("OSEON_AUTHORIZATION", ""),
        username=os.getenv("OSEON_USERNAME", ""),
        password=os.getenv("OSEON_PASSWORD", ""),
        user_header=os.getenv("OSEON_USER_HEADER", ""),
        terminal_header=os.getenv("OSEON_TERMINAL_HEADER", ""),
        api_version=os.getenv("OSEON_API_VERSION", "2.0"),
        allow_writes=enabled == "true",
        timeout=float(os.getenv("OSEON_TIMEOUT", "30")),
    )
