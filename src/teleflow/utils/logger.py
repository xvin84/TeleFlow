import sys
from pathlib import Path
from loguru import logger

def setup_logger() -> None:
    """Initialize application logger with rotation and formatting."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure log format
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    
    # Clean default handlers
    logger.remove()
    
    # Add stdout handler
    logger.add(sys.stdout, format=log_format, level="INFO", colorize=True)
    
    # Add file handler with rotation
    log_file = log_dir / "teleflow_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_file),
        format=log_format,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8"
    )
    
    logger.info("Logger initialized successfully.")

# Re-export logger for convenience
__all__ = ["logger", "setup_logger"]
