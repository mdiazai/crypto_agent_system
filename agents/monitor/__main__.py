import asyncio

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

from shared.config import settings
from shared.utils import configure_logging
from .monitor_agent import MonitorAgent


def main() -> None:
    configure_logging()

    if settings.sentry_dsn and sentry_sdk:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

    agent = MonitorAgent()
    asyncio.run(agent.start())


if __name__ == "__main__":
    main()
