import asyncio
import sentry_sdk

from shared.config import settings
from shared.utils import configure_logging
from .detector_agent import DetectorAgent


def main() -> None:
    configure_logging()

    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

    agent = DetectorAgent()
    asyncio.run(agent.start())


if __name__ == "__main__":
    main()
