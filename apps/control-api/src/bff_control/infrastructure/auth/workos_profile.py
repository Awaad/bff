"""WorkOS User Management profile adapter."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from bff_control.core.settings import WorkOSSettings
from bff_control.domains.authentication.provisioning_contracts import (
    ExternalUserProfileNotFoundError,
    ExternalUserProfileUnavailableError,
)
from bff_control.domains.authentication.provisioning_models import ExternalUserProfile


class WorkOSUserProfileClient:
    """Fetch trusted WorkOS User profile data for first-time provisioning."""

    def __init__(
        self,
        settings: WorkOSSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def fetch_user(self, subject: str) -> ExternalUserProfile:
        """Fetch and validate the WorkOS User identified by verified JWT `sub`."""

        encoded_subject = quote(subject, safe="")
        headers = {
            "Authorization": f"Bearer {self._settings.api_key.get_secret_value()}",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                base_url=str(self._settings.api_base_url).rstrip("/"),
                headers=headers,
                timeout=float(self._settings.user_request_timeout_seconds),
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"/user_management/users/{encoded_subject}",
                )
        except httpx.HTTPError as error:
            raise ExternalUserProfileUnavailableError(
                "provider profile request failed",
            ) from error

        if response.status_code == 404:
            raise ExternalUserProfileNotFoundError("provider user not found")

        if response.status_code != 200:
            raise ExternalUserProfileUnavailableError(
                "provider profile request failed",
            )

        try:
            payload: Any = response.json()
        except ValueError as error:
            raise ExternalUserProfileUnavailableError(
                "provider profile response was not valid JSON",
            ) from error

        if not isinstance(payload, dict):
            raise ExternalUserProfileUnavailableError(
                "provider profile response had invalid shape",
            )

        returned_subject = payload.get("id")
        email = payload.get("email")
        email_verified = payload.get("email_verified")
        display_name = payload.get("name")

        if returned_subject != subject:
            raise ExternalUserProfileUnavailableError(
                "provider profile subject mismatch",
            )
        if not isinstance(email, str) or not email.strip():
            raise ExternalUserProfileUnavailableError(
                "provider profile email was invalid",
            )
        if not isinstance(email_verified, bool):
            raise ExternalUserProfileUnavailableError(
                "provider profile email verification state was invalid",
            )
        if display_name is not None and not isinstance(display_name, str):
            raise ExternalUserProfileUnavailableError(
                "provider profile display name was invalid",
            )

        normalized_display_name = None
        if isinstance(display_name, str) and display_name.strip():
            normalized_display_name = display_name.strip()

        return ExternalUserProfile(
            subject=returned_subject,
            email=email.strip(),
            email_verified=email_verified,
            display_name=normalized_display_name,
        )
