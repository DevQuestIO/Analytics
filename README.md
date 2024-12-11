# DevQuest.IO - Analytics Service

## Overview
This analytics service microservice is a Python-based backend service for the Coding Progress Dashboard, responsible for processing, aggregating, and analyzing coding activity data.

## Features
- LeetCode data scraping and analysis
- Redis-based caching and task management
- Celery for asynchronous task processing
- Comprehensive logging and monitoring
- Pytest-based testing suite

## Tech Stack
- Python 3.10+
- FastAPI
- Celery
- Redis
- pytest
- Docker
- GraphQL integration

## Project Structure
```
.
├── Dockerfile
├── README.md
├── docker-compose.yaml
├── config.py
├── main.py
├── requirements.txt
├── filebeat/
│   └── filebeat.yml
├── logstash/
│   ├── config/
│   └── pipeline/
├── src/
│   ├── services/
│   ├── models/
│   └── utils/
├── tests/
│   └── test_analytics_service.py
└── pytest.ini
```

## Prerequisites
- Python 3.10+
- Docker
- Docker Compose
- Redis
- Celery
- FastAPI

## Environment Setup

### Virtual Environment
```bash
# Create virtual environment
python -m venv latest

# Activate virtual environment
# On Unix or MacOS
source latest/bin/activate
# On Windows
latest\Scripts\activate
```

### Installation
1. Clone the repository
```bash
git clone https://github.com/your-org/coding-progress-analytics-service.git
cd coding-progress-analytics-service
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

### Configuration
Create a `.env` file with the following configurations:
```
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=devquest.log

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

## Running the Service

### Development Mode
```bash
# Start Redis
docker-compose up redis

# Run main application
python main.py

# Run Celery worker
celery -A tasks worker --loglevel=info
```

### Docker Deployment
```bash
# Build docker image
docker-compose build

# Start all services
docker-compose up
```

## Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Generate HTML coverage report
pytest --cov=. --cov-report=html
```

## Key Components

### Modules
- `main.py`: Primary application entry point
- `tasks.py`: Celery background tasks
- `redis_service.py`: Redis interaction utilities
- `leetcode_service.py`: LeetCode data scraping and processing
- `leetcode_graphql.py`: GraphQL interactions
- `models.py`: Data models and schemas
- `logging_config.py`: Logging configuration

### Logging
- Configured log file: `devquest.log`
- Supports different log levels (DEBUG, INFO, WARNING, ERROR)
- Integrated with Filebeat for log management

### Task Processing
- Celery for asynchronous task management
- Background tasks for data scraping and processing
- Redis as message broker and result backend

## Monitoring and Observability
- Filebeat for log shipping
- Logstash for log processing
- Configurable logging levels
- Comprehensive error tracking

## Continuous Integration
- pytest for unit and integration testing
- Code coverage reporting
- GitHub Actions workflow (recommended)


## Troubleshooting
- Ensure Redis is running
- Check `.env` file configurations
- Verify Python and dependency versions
- Review Celery worker logs
- Check network connectivity

## License
Distributed under the MIT License. See `LICENSE` for more information.