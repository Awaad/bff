"""Application-generated identifiers."""

from __future__ import annotations

import secrets
import time
from uuid import UUID

_UNIX_MS_BITS = 48
_RAND_A_BITS = 12
_RAND_B_BITS = 62


def uuid7() -> UUID:
    """Generate an RFC 9562 UUIDv7 using Unix milliseconds plus CSPRNG bits."""

    unix_ms = time.time_ns() // 1_000_000
    if unix_ms >= 1 << _UNIX_MS_BITS:
        raise OverflowError("current Unix millisecond timestamp does not fit UUIDv7")

    value = unix_ms << 80
    value |= 0x7 << 76
    value |= secrets.randbits(_RAND_A_BITS) << 64
    value |= 0b10 << 62
    value |= secrets.randbits(_RAND_B_BITS)

    return UUID(int=value)
