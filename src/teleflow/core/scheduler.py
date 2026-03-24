"""
SchedulerManager — APScheduler 4.x в отдельном потоке.

APScheduler 4.x использует anyio, который несовместим с qasync в одном
event loop. Решение: запускаем scheduler в отдельном потоке со своим
asyncio event loop. Взаимодействие через run_coroutine_threadsafe.

Windows fix: используем WindowsSelectorEventLoopPolicy в потоке планировщика,
потому что ProactorEventLoop (дефолт на Windows) не совместим с anyio/aiosqlite
в этом контексте.
"""
from __future__ import annotations

import asyncio
import random
import sys
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler import AsyncScheduler
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.abc import Trigger

from teleflow.core.sender_engine import SenderEngine
from teleflow.core.telegram.client import TeleflowClient
from teleflow.core.dispatch import dispatch_scheduled_send
from teleflow.utils.logger import logger


# ── RandomWindowTrigger ───────────────────────────────────────────────────────

class RandomWindowTrigger(Trigger):
    """Fires once per day at a random time within [start_hhmm, end_hhmm]."""

    def __init__(self, start_hhmm: str, end_hhmm: str, timezone: str = "local") -> None:
        sh, sm = map(int, start_hhmm.split(":"))
        eh, em = map(int, end_hhmm.split(":"))
        self._start_minutes = sh * 60 + sm
        self._end_minutes   = eh * 60 + em
        if self._end_minutes <= self._start_minutes:
            raise ValueError("end_hhmm must be strictly after start_hhmm")
        self._tz_name = timezone
        self._tz: Any = self._resolve_tz(timezone)

    @staticmethod
    def _resolve_tz(tz_name: str) -> Any:
        if tz_name == "local":
            return datetime.now().astimezone().tzinfo
        try:
            return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, KeyError):
            return datetime.now().astimezone().tzinfo

    def _random_fire_for_date(self, base_date: datetime) -> datetime:
        offset = random.randint(self._start_minutes, self._end_minutes - 1)
        return base_date.replace(
            hour=offset // 60,
            minute=offset % 60,
            second=random.randint(0, 59),
            microsecond=0,
        )

    def next(self) -> datetime | None:
        now = datetime.now(tz=self._tz)
        today_base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        candidate = self._random_fire_for_date(today_base)
        if candidate > now:
            return candidate
        tomorrow = today_base + timedelta(days=1)
        return self._random_fire_for_date(tomorrow)

    def __getstate__(self) -> dict[str, Any]:
        return {
            "start_minutes": self._start_minutes,
            "end_minutes": self._end_minutes,
            "tz_name": self._tz_name,
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        self._start_minutes = state["start_minutes"]
        self._end_minutes   = state["end_minutes"]
        self._tz_name = state.get("tz_name", "local")
        self._tz = self._resolve_tz(self._tz_name)


# ── ScheduleConfig ────────────────────────────────────────────────────────────

class ScheduleConfig:
    MODES = ("one_time", "daily_fixed", "weekday", "interval", "random_window")

    def __init__(
        self,
        mode: str,
        *,
        run_datetime: datetime | None = None,
        time_hhmm: str = "10:00",
        weekdays: list[str] | None = None,
        interval_minutes: int = 60,
        window_start: str = "10:00",
        window_end: str = "11:00",
        timezone: str = "local",
    ) -> None:
        if mode not in self.MODES:
            raise ValueError(f"Unknown mode {mode!r}")
        self.mode = mode
        self.run_datetime = run_datetime
        self.time_hhmm = time_hhmm
        self.weekdays: list[str] = weekdays or []
        self.interval_minutes = interval_minutes
        self.window_start = window_start
        self.window_end = window_end
        self.timezone = timezone

    def build_trigger(self) -> Trigger:
        tz = None if self.timezone == "local" else self.timezone
        if self.mode == "one_time":
            return DateTrigger(run_time=self.run_datetime or datetime.now())
        if self.mode == "daily_fixed":
            h, m = map(int, self.time_hhmm.split(":"))
            kw: dict[str, Any] = {"hour": h, "minute": m, "second": 0}
            if tz:
                kw["timezone"] = tz
            return CronTrigger(**kw)
        if self.mode == "weekday":
            h, m = map(int, self.time_hhmm.split(":"))
            dow = ",".join(self.weekdays) if self.weekdays else "*"
            kw = {"day_of_week": dow, "hour": h, "minute": m, "second": 0}
            if tz:
                kw["timezone"] = tz
            return CronTrigger(**kw)
        if self.mode == "interval":
            return IntervalTrigger(minutes=self.interval_minutes)
        if self.mode == "random_window":
            return RandomWindowTrigger(self.window_start, self.window_end, self.timezone)
        raise ValueError(f"Unreachable: {self.mode!r}")

    def human_description(self) -> str:
        if self.mode == "one_time":
            dt = self.run_datetime
            ts = dt.strftime("%d.%m.%Y %H:%M") if dt else "—"
            return f"Один раз: {ts}"
        if self.mode == "daily_fixed":
            return f"Ежедневно в {self.time_hhmm}"
        if self.mode == "weekday":
            day_map = {
                "mon": "Пн", "tue": "Вт", "wed": "Ср", "thu": "Чт",
                "fri": "Пт", "sat": "Сб", "sun": "Вс",
            }
            days = ", ".join(day_map.get(d, d) for d in self.weekdays) or "каждый день"
            return f"{days} в {self.time_hhmm}"
        if self.mode == "interval":
            h, m = divmod(self.interval_minutes, 60)
            if h and m:
                return f"Каждые {h}ч {m}мин"
            if h:
                return f"Каждые {h}ч"
            return f"Каждые {m}мин"
        if self.mode == "random_window":
            return f"Случайно: {self.window_start}–{self.window_end}"
        return self.mode


# ── SchedulerManager ──────────────────────────────────────────────────────────

_DB_URL = "sqlite+aiosqlite:///teleflow_scheduler.db"


class SchedulerManager:
    """APScheduler 4.x в отдельном потоке со своим event loop.

    Изолирует anyio от qasync, устраняя RuntimeError 'Cannot enter into task'.
    Взаимодействие через run_coroutine_threadsafe — полностью thread-safe.
    """

    def __init__(self, sender_engine: SenderEngine) -> None:
        self.sender = sender_engine
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_loop: asyncio.AbstractEventLoop | None = None  # Qt/qasync main loop
        self._scheduler: AsyncScheduler | None = None
        self._ready = threading.Event()
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._main_loop = asyncio.get_event_loop()
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="apscheduler"
        )
        self._thread.start()
        if not self._ready.wait(timeout=10.0):
            logger.error("APScheduler thread did not become ready in time!")
        else:
            logger.info("APScheduler 4.x started in background thread.")

    def _thread_main(self) -> None:
        # ── Windows fix ───────────────────────────────────────────────────────
        # On Windows the default event loop policy creates a ProactorEventLoop.
        # anyio (used internally by APScheduler 4.x) and aiosqlite both work
        # better with the SelectorEventLoop in this secondary thread context.
        # Setting the policy here affects only this thread's new event loop.
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_scheduler())
        except Exception as e:
            logger.error(f"APScheduler thread crashed: {e}")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _run_scheduler(self) -> None:
        from apscheduler import Event, JobReleased  # noqa: PLC0415
        data_store = SQLAlchemyDataStore(_DB_URL)
        self._scheduler = AsyncScheduler(data_store=data_store)

        async def _on_job_released(event: Event) -> None:
            """Clean up one_time schedule metadata after it fires."""
            if not isinstance(event, JobReleased):
                return
            schedule_id = getattr(event, "schedule_id", None)
            if not schedule_id:
                return
            if not schedule_id.startswith("sched_"):
                return
            # Delete from teleflow.db on the main event loop
            if self._main_loop and self._main_loop.is_running():
                from teleflow.core.storage.db import db  # noqa: PLC0415
                asyncio.run_coroutine_threadsafe(
                    db.delete_schedule(schedule_id), self._main_loop
                )
                logger.info(f"Cleaned up one_time schedule {schedule_id} after execution.")

        try:
            async with self._scheduler:
                self._scheduler.subscribe(_on_job_released)
                self._ready.set()
                await self._scheduler.run_until_stopped()
        except Exception as e:
            logger.error(f"APScheduler error: {e}")
        finally:
            self._ready.clear()

    async def shutdown(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._scheduler and self._loop and self._loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(
                self._scheduler.stop(), self._loop
            )
            try:
                fut.result(timeout=5.0)
            except Exception as e:
                logger.warning(f"Scheduler stop error: {e}")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("APScheduler stopped.")

    # ── Public API ────────────────────────────────────────────────────────────

    def add_schedule(
        self,
        config: ScheduleConfig,
        client: TeleflowClient,
        phone: str,
        msg_id: int,
        text: str,
        media_path: str | None,
    ) -> str:
        """Submit a schedule from the main thread. Fully thread-safe."""
        if not self._loop or not self._scheduler:
            logger.error("Scheduler not running — cannot add schedule")
            return ""
        trigger = config.build_trigger()
        schedule_id = f"sched_{msg_id}_{uuid.uuid4().hex[:8]}"

        fut = asyncio.run_coroutine_threadsafe(
            self._scheduler.add_schedule(
                dispatch_scheduled_send,
                trigger=trigger,
                id=schedule_id,
                args=[phone, msg_id, text, media_path],
            ),
            self._loop,
        )

        def _on_done(f: Any) -> None:
            exc = f.exception()
            if exc:
                logger.error(f"Failed to persist schedule {schedule_id}: {exc!r}")
            else:
                logger.info(f"Schedule {schedule_id} persisted to DB.")

        fut.add_done_callback(_on_done)
        logger.info(f"Submitted schedule {schedule_id} (mode={config.mode}, msg={msg_id})")
        return schedule_id

    def schedule_send_job(
        self,
        run_date: datetime,
        client: TeleflowClient,
        phone: str,
        msg_id: int,
        text: str,
        media_path: str | None,
    ) -> str:
        """Backward-compatible one-time schedule."""
        cfg = ScheduleConfig(mode="one_time", run_datetime=run_date)
        return self.add_schedule(cfg, client, phone, msg_id, text, media_path)

    async def list_schedules(self) -> list[dict[str, Any]]:
        if not self._loop or not self._scheduler:
            return []
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self._scheduler.get_schedules(), self._loop
            )
            schedules = fut.result(timeout=3.0)
            return [
                {
                    "id": s.id,
                    "next_fire_time": (
                        s.next_fire_time.strftime("%d.%m.%Y %H:%M:%S")
                        if s.next_fire_time else "—"
                    ),
                    "paused": s.paused,
                }
                for s in schedules
            ]
        except Exception as e:
            logger.error(f"Failed to list schedules: {e}")
            return []

    def remove_schedule(self, schedule_id: str) -> None:
        """Remove a schedule from APScheduler and from the metadata DB."""
        if not self._loop or not self._scheduler:
            logger.error("Scheduler not running — cannot remove schedule")
            return
        fut = asyncio.run_coroutine_threadsafe(
            self._scheduler.remove_schedule(schedule_id), self._loop
        )
        try:
            fut.result(timeout=3.0)
            logger.info(f"Schedule {schedule_id} removed from APScheduler.")
        except Exception as e:
            logger.error(f"Failed to remove schedule {schedule_id}: {e}")

    def pause_schedule(self, schedule_id: str) -> None:
        """Pause a schedule in APScheduler."""
        if not self._loop or not self._scheduler:
            return
        fut = asyncio.run_coroutine_threadsafe(
            self._scheduler.pause_schedule(schedule_id), self._loop
        )
        try:
            fut.result(timeout=3.0)
            logger.info(f"Schedule {schedule_id} paused.")
        except Exception as e:
            logger.error(f"Failed to pause schedule {schedule_id}: {e}")

    def resume_schedule(self, schedule_id: str) -> None:
        """Resume a paused schedule in APScheduler."""
        if not self._loop or not self._scheduler:
            return
        fut = asyncio.run_coroutine_threadsafe(
            self._scheduler.unpause_schedule(schedule_id), self._loop
        )
        try:
            fut.result(timeout=3.0)
            logger.info(f"Schedule {schedule_id} resumed.")
        except Exception as e:
            logger.error(f"Failed to resume schedule {schedule_id}: {e}")

    @property
    def running(self) -> bool:
        return self._running
