"""Unwritten Dao world server."""

from world_server.app import create_app

app = create_app()

__all__ = ["app", "create_app"]
