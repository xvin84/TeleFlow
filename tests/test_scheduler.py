"""
Unit tests for teleflow.core.scheduler.ScheduleConfig

Tests trigger construction and human_description() for all 5 modes
without starting APScheduler or any Qt/Telegram dependencies.
"""
import pytest
from datetime import datetime, timezone

from teleflow.core.scheduler import ScheduleConfig, RandomWindowTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger


class TestScheduleConfigValidation:
    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown mode"):
            ScheduleConfig(mode="invalid_mode")

    def test_all_valid_modes(self) -> None:
        for mode in ("one_time", "daily_fixed", "weekday", "interval", "random_window"):
            cfg = ScheduleConfig(mode=mode)
            assert cfg.mode == mode


class TestBuildTrigger:
    def test_one_time_returns_date_trigger(self) -> None:
        dt = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        cfg = ScheduleConfig(mode="one_time", run_datetime=dt)
        trigger = cfg.build_trigger()
        assert isinstance(trigger, DateTrigger)

    def test_daily_fixed_returns_cron_trigger(self) -> None:
        cfg = ScheduleConfig(mode="daily_fixed", time_hhmm="09:30")
        trigger = cfg.build_trigger()
        assert isinstance(trigger, CronTrigger)

    def test_weekday_returns_cron_trigger(self) -> None:
        cfg = ScheduleConfig(mode="weekday", weekdays=["mon", "wed", "fri"], time_hhmm="08:00")
        trigger = cfg.build_trigger()
        assert isinstance(trigger, CronTrigger)

    def test_interval_returns_interval_trigger(self) -> None:
        cfg = ScheduleConfig(mode="interval", interval_minutes=90)
        trigger = cfg.build_trigger()
        assert isinstance(trigger, IntervalTrigger)

    def test_random_window_returns_custom_trigger(self) -> None:
        cfg = ScheduleConfig(mode="random_window", window_start="10:00", window_end="12:00")
        trigger = cfg.build_trigger()
        assert isinstance(trigger, RandomWindowTrigger)

    def test_random_window_invalid_range_raises(self) -> None:
        cfg = ScheduleConfig(mode="random_window", window_start="12:00", window_end="10:00")
        with pytest.raises(ValueError):
            cfg.build_trigger()


class TestHumanDescription:
    def test_one_time(self) -> None:
        dt = datetime(2026, 3, 17, 22, 13)
        cfg = ScheduleConfig(mode="one_time", run_datetime=dt)
        desc = cfg.human_description()
        assert "17.03.2026" in desc
        assert "22:13" in desc

    def test_daily_fixed(self) -> None:
        cfg = ScheduleConfig(mode="daily_fixed", time_hhmm="10:00")
        assert "10:00" in cfg.human_description()
        assert "Ежедневно" in cfg.human_description()

    def test_weekday(self) -> None:
        cfg = ScheduleConfig(mode="weekday", weekdays=["mon", "fri"], time_hhmm="09:00")
        desc = cfg.human_description()
        assert "Пн" in desc
        assert "Пт" in desc
        assert "09:00" in desc

    def test_interval_hours(self) -> None:
        cfg = ScheduleConfig(mode="interval", interval_minutes=120)
        assert "2ч" in cfg.human_description()

    def test_interval_minutes(self) -> None:
        cfg = ScheduleConfig(mode="interval", interval_minutes=45)
        assert "45мин" in cfg.human_description()

    def test_interval_mixed(self) -> None:
        cfg = ScheduleConfig(mode="interval", interval_minutes=90)
        desc = cfg.human_description()
        assert "1ч" in desc
        assert "30мин" in desc

    def test_random_window(self) -> None:
        cfg = ScheduleConfig(mode="random_window", window_start="10:00", window_end="12:00")
        desc = cfg.human_description()
        assert "10:00" in desc
        assert "12:00" in desc


class TestRandomWindowTrigger:
    def test_next_fire_is_in_window(self) -> None:
        trigger = RandomWindowTrigger("09:00", "11:00")
        next_dt = trigger.next()
        assert next_dt is not None
        total_minutes = next_dt.hour * 60 + next_dt.minute
        assert 9 * 60 <= total_minutes < 11 * 60

    def test_next_fire_is_in_future(self) -> None:
        trigger = RandomWindowTrigger("00:00", "23:59")
        next_dt = trigger.next()
        assert next_dt is not None
        assert next_dt > datetime.now(tz=next_dt.tzinfo)

    def test_pickle_roundtrip(self) -> None:
        import pickle
        trigger = RandomWindowTrigger("10:00", "12:00", "UTC")
        restored = pickle.loads(pickle.dumps(trigger))
        assert restored._start_minutes == trigger._start_minutes
        assert restored._end_minutes   == trigger._end_minutes
        assert restored._tz_name       == trigger._tz_name
