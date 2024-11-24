import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        record_dict: Dict[str, Any] = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            record_dict['exception'] = self.formatException(record.exc_info)
            
        # Add extra fields
        if hasattr(record, 'extra_fields'):
            record_dict.update(record.extra_fields)
            
        return json.dumps(record_dict)

def setup_logging(service_name: str = 'analytics', level: str = 'INFO') -> None:
    """Setup structured logging"""
    root_logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)
    
    # Create console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    
    # Set logging level
    root_logger.setLevel(level)
    root_logger.addHandler(handler)
    
    # Add service name to all logs
    logging.LogRecord = type('LogRecord', (logging.LogRecord,), {
        'extra_fields': {'service': service_name}
    })