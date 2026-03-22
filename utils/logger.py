import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True,
    )
    log_dir = Path.home() / "AppData" / "Local" / "trevo" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "trevo_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="1 day",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    )


setup_logger()

__all__ = ["logger"]
