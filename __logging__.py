import os

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def get_logger_config():
    return {
        "version": 1,
        "disable_existing_loggers": False,

        "formatters": {
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "fmt": (
                    "%(asctime)s "
                    "%(levelname)s "
                    "%(name)s "
                    "%(message)s "
                    "%(pathname)s "
                    "%(lineno)d "
                    "%(funcName)s "
                    "%(process)d "
                    "%(thread)d "
                    "%(request_id)s"
                ),
                "datefmt": "%Y-%m-%d %H:%M:%S%z",
            },
        },

        "filters": {
            "request_id": {
                "()": "request_id.logging.RequestIdFilter"
            },
        },

        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "filters": ["request_id"],
            },
        },

        "root": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
        },

        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },

            "django.request": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },

            "django.db.backends": {
                "handlers": ["console"],
                "level": os.getenv("DJANGO_SQL_LOG_LEVEL", "WARNING"),
                "propagate": False,
            },

            "rest_framework": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },

            "gunicorn.error": {
                "level": LOG_LEVEL,
                "handlers": ["console"],
                "propagate": False,
            },
            "gunicorn.access": {
                "level": LOG_LEVEL,
                "handlers": ["console"],
                "propagate": False,
            },

            "celery": {
                "handlers": ["console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
        },
    }
