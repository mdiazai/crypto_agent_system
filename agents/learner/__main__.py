import asyncio
import sentry_sdk

from shared.config import settings
from shared.utils import configure_logging
from .learner_agent import LearnerAgent


def main() -> None:
    configure_logging()

    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

    agent = LearnerAgent()
    asyncio.run(agent.start())


if __name__ == "__main__":
    main()
