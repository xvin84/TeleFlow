import sys
import asyncio
import qasync
import signal
from teleflow.utils.logger import setup_logger, logger
from teleflow.gui.app import TeleFlowApp

async def async_main(app: TeleFlowApp) -> None:
    """Async main routine to start the app."""
    try:
        await app.run()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"Critical error during async application runtime: {e}")

def main() -> int:
    """Entry point for the TeleFlow application."""
    setup_logger()
    logger.info("Starting TeleFlow application...")

    app = TeleFlowApp()

    # Setup qasync event loop
    loop = qasync.QEventLoop(app.app)
    asyncio.set_event_loop(loop)

    # Properly handle Ctrl+C to avoid noisy threading tracebacks
    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, loop.stop)

    try:
        with loop:
            loop.create_task(async_main(app))
            loop.run_forever()

            # ── Graceful cleanup ─────────────────────────────────────────
            # The Qt event loop has stopped, but we are still inside the
            # 'with loop' block, so the asyncio loop is still open and
            # we can run one final coroutine to cleanly disconnect all
            # Telethon clients / shutdown the scheduler / close the DB.
            # Without this step the process hangs because Telethon's TCP
            # sockets are never closed.
            try:
                loop.run_until_complete(
                    asyncio.wait_for(app.cleanup(), timeout=6.0)
                )
            except Exception as e:
                logger.warning(f"Cleanup error (non-fatal): {e}")

            return 0
    except KeyboardInterrupt:
        logger.info("Application closed by user (KeyboardInterrupt).")
        return 0
    except Exception as e:
        logger.exception(f"Critical error in event loop: {e}")
        return 1
    finally:
        logger.info("Application shut down.")

if __name__ == "__main__":
    sys.exit(main())
