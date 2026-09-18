"""Transport-level exceptions expressed through the public problem registry."""

from __future__ import annotations

from bff_control.api.problems.schemas import ProblemCode


class ProblemException(Exception):
    """Transport-level request failure expressed through the problem registry."""

    def __init__(
        self,
        code: ProblemCode,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.headers = dict(headers or {})
