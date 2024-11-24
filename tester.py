# logging_config.py
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            '@timestamp': datetime.utcnow().isoformat(),
            'service': 'analytics',
            'level': record.levelname,
            'message': record.getMessage(),
            'logger_name': record.name,
            'module': record.module,
            'function': record.funcName,
            'line_number': record.lineno,
            'path': record.pathname
        }
        
        # Add extra fields if they exist
        print(record.__dict__, "hereee")
        # if hasattr(record, 'extra'):
        #     log_entry.update(record.extra)
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if not (key.startswith('_') or key in ['msg', 'args', 'exc_info', 'exc_text', 'name', 
                   'levelno', 'levelname', 'pathname', 'filename', 'module', 'lineno', 
                   'funcName', 'created', 'msecs', 'relativeCreated', 'thread', 'threading',
                   'processName', 'process'])
        }
        log_entry.update(extra_fields)
            
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # Console handler with JSON formatting
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    
    return logger

# Example usage in your service
logger = setup_logging()

# Add some test logs
logger.info("Test log message", extra={
    'test_id': 123,
    'environment': 'development'
})