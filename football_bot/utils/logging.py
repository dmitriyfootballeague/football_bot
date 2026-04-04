import logging.config
import logging

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[%(asctime)s.%(msecs)03d] (%(levelname)s) {%(name)s:%(funcName)s:%(lineno)s}: %(message)s',
            'datefmt': DATETIME_FORMAT
        },
    },
    'handlers': {
        'console.info': {
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',  # Default is stderr
        },
        'file.info': {
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': f'rotate_bot.log',
        },
        'console.debug': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        }
    },
    'loggers': {
        '': {  # root logger
            'handlers': ['console.info'],
            'level': 'INFO',
            'propagate': True
        },
        'development': {
            'handlers': ['console.debug'],
            'level': 'DEBUG',
            'propagate': False
        },
    }
}
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)
