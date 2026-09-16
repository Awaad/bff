"""ASGI entrypoint for the control API."""

from bff_control.bootstrap import create_application

app = create_application()
