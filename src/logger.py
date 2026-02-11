"""
Structured logging for AIDEV-OPS.

Provides per-project log files, console + file handlers,
color output, and automatic log rotation.
"""

import os
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime

try:
    import colorlog
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False


# Module-level logger cache
_loggers = {}


def setup_logger(name, config, project_name=None):
    """
    Create or return a structured logger.

    Args:
        name: Logger name (module name)
        config: Application config dict
        project_name: Optional project name for project-specific logs

    Returns:
        logging.Logger instance
    """
    cache_key = f"{name}:{project_name or 'system'}"
    if cache_key in _loggers:
        return _loggers[cache_key]

    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO').upper())
    log_dir = Path(log_config.get('dir', '/opt/aidev/logs'))
    max_size = log_config.get('max_size_mb', 50) * 1024 * 1024  # Convert to bytes
    backup_count = log_config.get('backup_count', 5)
    log_format = log_config.get('format', '%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    # Create log directory
    if project_name:
        project_log_dir = log_dir / project_name
        project_log_dir.mkdir(parents=True, exist_ok=True)
        log_file = project_log_dir / f"{name}.log"
    else:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{name}.log"

    # Create logger
    logger = logging.getLogger(cache_key)
    logger.setLevel(log_level)

    # Avoid duplicate handlers
    if logger.handlers:
        _loggers[cache_key] = logger
        return logger

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)

    # Console handler with color
    if HAS_COLOR:
        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(log_level)
        color_format = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(name)s: %(message)s",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        console_handler.setFormatter(color_format)
    else:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter(log_format))

    logger.addHandler(console_handler)

    _loggers[cache_key] = logger
    return logger


def get_logger(name):
    """
    Get an existing logger by name, or create a basic one.

    Args:
        name: Logger name

    Returns:
        logging.Logger instance
    """
    if name in _loggers:
        return _loggers[name]

    # Create a basic logger if config isn't available yet
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger


def log_separator(logger, title="", char="=", width=60):
    """Log a visual separator line."""
    if title:
        padding = (width - len(title) - 2) // 2
        line = f"{char * padding} {title} {char * padding}"
    else:
        line = char * width
    logger.info(line)
