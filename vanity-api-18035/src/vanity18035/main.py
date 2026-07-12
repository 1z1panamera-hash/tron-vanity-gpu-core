from __future__ import annotations

from aiohttp import web

from .api import build_ssl_context, create_app
from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    settings.validate()
    web.run_app(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        ssl_context=build_ssl_context(settings),
        access_log_format='%a "%r" %s %Tf',
    )


if __name__ == "__main__":
    main()
