import asyncio
import sentry_sdk

from shared.config import settings
from shared.utils import configure_logging
from .executor_agent import ExecutorAgent


def main() -> None:
    configure_logging()

    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

    if not settings.paper_trading:
        import structlog
        log = structlog.get_logger(__name__)
        log.warning(
            "executor_agent.REAL_TRADING_MODE",
            msg="⚠️  PAPER_TRADING=false — las órdenes se ejecutarán en los exchanges reales.",
            capital_total=settings.capital_total_usd,
            mexc_capital=settings.mexc_capital_usd,
            bitget_capital=settings.bitget_capital_usd,
        )

    agent = ExecutorAgent()
    asyncio.run(agent.start())


if __name__ == "__main__":
    main()
