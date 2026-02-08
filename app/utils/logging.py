import logging
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "users": {  # твой логгер
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "email": {  # логгер для сервиса отправки писем
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn": {  # включаем логи uvicorn
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "level": "ERROR",
        },
        "uvicorn.access": {  # access logs
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
