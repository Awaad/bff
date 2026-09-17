"""Provider-neutral authenticated-token evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class VerifiedAccessToken:
    """Claims trusted only after provider signature/policy verification."""

    issuer: str
    subject: str
    provider_session_id: str
    token_id: str
    issued_at: datetime
    expires_at: datetime
