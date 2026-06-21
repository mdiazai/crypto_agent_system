import asyncio
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from shared.models import get_session, DiagnosticsLog

from .health_checker import HealthChecker
from .claude_diagnostics import ClaudeDiagnostics
from .telegram_notifier import TelegramNotifier

log = structlog.get_logger(__name__)

CYCLE_INTERVAL_MINUTES = 30
OK_HEARTBEAT_EVERY = 6  # send OK ping every N ok-cycles (~3h)


class SmartDevopsAgent:
    def __init__(self) -> None:
        self._checker = HealthChecker()
        self._diagnostics = ClaudeDiagnostics()
        self._notifier = TelegramNotifier()
        self._scheduler = AsyncIOScheduler()
        self._ok_cycle_count = 0

    async def start(self) -> None:
        log.info("smartdevops_agent.starting")

        self._scheduler.add_job(
            self.run_cycle,
            trigger="interval",
            minutes=CYCLE_INTERVAL_MINUTES,
            id="smartdevops_cycle",
            replace_existing=True,
            max_instances=1,
        )
        self._scheduler.start()
        log.info(
            "smartdevops_agent.scheduled",
            interval_minutes=CYCLE_INTERVAL_MINUTES,
        )

        await self.run_cycle()

        try:
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            self._scheduler.shutdown(wait=False)

    async def run_cycle(self) -> None:
        log.info("smartdevops_agent.cycle_started")

        # Don't pile up proposals if one is already pending approval
        if await self._notifier.has_pending_command():
            log.info("smartdevops_agent.pending_exists_skipping")
            return

        snapshot = await self._checker.collect()
        diagnosis = await self._diagnostics.diagnose(snapshot)

        severity = diagnosis["severity"]
        diag_text = diagnosis["diagnosis"]
        fix_command = diagnosis["fix_command"]

        await self._save_to_db(severity, diag_text, fix_command)

        if severity == "ok":
            self._ok_cycle_count += 1
            if self._ok_cycle_count % OK_HEARTBEAT_EVERY == 0:
                await self._notifier.send_ok_heartbeat(diag_text, self._ok_cycle_count)
        else:
            self._ok_cycle_count = 0
            await self._notifier.send_proposal(severity, diag_text, fix_command)

        log.info(
            "smartdevops_agent.cycle_done",
            severity=severity,
            has_fix=fix_command is not None,
        )

    async def _save_to_db(
        self, severity: str, diagnosis: str, fix_command: str | None
    ) -> None:
        try:
            async with get_session() as session:
                entry = DiagnosticsLog(
                    run_at=datetime.now(timezone.utc),
                    severity=severity,
                    diagnosis=diagnosis,
                    fix_command=fix_command,
                )
                session.add(entry)
        except Exception as e:
            log.warning("smartdevops_agent.db_save_error", error=str(e))
