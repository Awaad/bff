from __future__ import annotations

from uuid import RFC_4122

from bff_control.core.ids import uuid7


def test_uuid7_uses_rfc_variant_and_version() -> None:
    value = uuid7()

    assert value.version == 7
    assert value.variant == RFC_4122
