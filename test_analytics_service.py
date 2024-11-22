# tests/services/test_analytics_service.py
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from models import (
    UserProgress, 
    Question, 
    PlatformProgress, 
    AggregatedStats, 
    ProgressData
)
from leetcode_service import LeetCodeService, LeetCodeSubmission

class MockLeetCodeSubmission:
    """Mock submission that matches the structure expected by the service"""
    def __init__(
        self,
        id: int,
        question_id: int,
        title: str,
        status_display: str,
        timestamp: int
    ):
        self.id = id
        self.question_id = question_id
        self.title = title
        self.status_display = status_display
        self.timestamp = timestamp
        self.title_slug = "test-slug"
        self.runtime = "100ms"
        self.memory = "10MB"
        self.lang = "python"

@pytest.fixture
def mock_leetcode_service():
    """Create a mock LeetCode service"""
    class MockService:
        def __init__(self):
            self.fetch_all_submissions = AsyncMock()
            self._get_difficulty = Mock(return_value="medium")
            self._get_topics = Mock(return_value=["arrays", "hash-table"])
    return MockService()

@pytest.fixture
def mock_graphql_service():
    """Create a mock graphql service"""
    class MockService:
        def __init__(self):
            self.fetch_all_stats = AsyncMock()
    return MockService()

@pytest.mark.asyncio
async def test_empty_submissions(mock_leetcode_service, mongodb, mock_graphql_service):
    """Test handling of empty submissions list"""
    # Arrange
    mock_leetcode_service.fetch_all_submissions.return_value = []
    mock_graphql_service.fetch_all_stats.return_value = (None, None, None, None, None)
    
    from leetcode_service import AnalyticsService
    analytics_service = AnalyticsService()
    analytics_service.leetcode_service = mock_leetcode_service
    analytics_service.graphql_service = mock_graphql_service

    # Create a clean state
    await mongodb.user_progress.delete_many({})

    # Act
    result = await analytics_service.sync_user_submissions(
        user_id="test_user",
        username="test",
        csrf_token="token",
        cookie="cookie"
    )
    print(result)

    # Assert
    assert result is not None
    assert result.progress_data.leetcode is not None
    # Get the actual count from database to verify
    count = await UserProgress.find({"user_id": "test_user"}).count()
    assert count == 1  # Should have one document
    assert len(result.progress_data.leetcode.questions) == 0
    assert result.aggregated_stats.total_solved == 0

@pytest.mark.asyncio
async def test_first_time_sync(mock_leetcode_service, mongodb):
    """Test first-time sync for a new user"""
    # Arrange
    current_time = int(datetime.now().timestamp())
    
    # Create two mock submissions
    mock_submissions = [
        MockLeetCodeSubmission(
            id=1,
            question_id=1,
            title="Two Sum",
            status_display="Accepted",
            timestamp=current_time
        ),
        MockLeetCodeSubmission(
            id=2,
            question_id=2,
            title="Add Two Numbers",
            status_display="Accepted",
            timestamp=current_time - 3600
        )
    ]
    
    mock_leetcode_service.fetch_all_submissions.return_value = mock_submissions
    
    from leetcode_service import AnalyticsService
    analytics_service = AnalyticsService()
    analytics_service.leetcode_service = mock_leetcode_service

    # Act
    result = await analytics_service.sync_user_submissions(
        user_id="test_user",
        username="test",
        csrf_token="token",
        cookie="cookie"
    )

    # Assert
    assert result is not None
    assert result.user_id == "test_user"
    assert result.progress_data.leetcode is not None
    assert len(result.progress_data.leetcode.questions) == 2
    
    # Verify questions are correctly stored
    questions = result.progress_data.leetcode.questions
    assert len([q for q in questions if q.status == "solved"]) == 2

@pytest.mark.asyncio
async def test_sync_with_existing_data(mock_leetcode_service, mongodb):
    """Test sync with existing data"""
    # Arrange
    current_time = int(datetime.now().timestamp())
    
    # Create existing progress
    existing_progress = UserProgress(
        user_id="test_user",
        progress_data=ProgressData(
            leetcode=PlatformProgress(
                questions=[
                    Question(
                        id="1",
                        name="Two Sum",
                        difficulty="medium",
                        topics=["arrays"],
                        status="solved",
                        attempts=1,
                        time_spent=10,
                        last_attempted=datetime.fromtimestamp(current_time - 7200),
                        submission_id=1
                    )
                ]
            ),
            geeksforgeeks=None
        ),
        aggregated_stats=AggregatedStats(total_solved=1)
    )
    await existing_progress.save()

    # Create mock submissions
    mock_submissions = [
        MockLeetCodeSubmission(
            id=2,
            question_id=2,
            title="Add Two Numbers",
            status_display="Accepted",
            timestamp=current_time
        )
    ]
    
    mock_leetcode_service.fetch_all_submissions.return_value = mock_submissions
    
    from leetcode_service import AnalyticsService
    analytics_service = AnalyticsService()
    analytics_service.leetcode_service = mock_leetcode_service

    # Act
    result = await analytics_service.sync_user_submissions(
        user_id="test_user",
        username="test",
        csrf_token="token",
        cookie="cookie"
    )

    # Assert
    assert result is not None
    assert len(result.progress_data.leetcode.questions) == 2  # One existing + one new
    questions = result.progress_data.leetcode.questions
    question_ids = {q.id for q in questions}
    assert "1" in question_ids  # Existing question
    assert "2" in question_ids  # New question

@pytest.mark.asyncio
async def test_sync_with_different_submission_status(mock_leetcode_service, mongodb):
    """Test sync with different submission statuses"""
    # Arrange
    current_time = int(datetime.now().timestamp())
    
    mock_submissions = [
        MockLeetCodeSubmission(
            id=1,
            question_id=1,
            title="Question 1",
            status_display="Accepted",
            timestamp=current_time
        ),
        MockLeetCodeSubmission(
            id=2,
            question_id=2,
            title="Question 2",
            status_display="Wrong Answer",
            timestamp=current_time - 3600
        ),
        MockLeetCodeSubmission(
            id=3,
            question_id=3,
            title="Question 3",
            status_display="Runtime Error",
            timestamp=current_time - 7200
        )
    ]
    
    mock_leetcode_service.fetch_all_submissions.return_value = mock_submissions
    
    from leetcode_service import AnalyticsService
    analytics_service = AnalyticsService()
    analytics_service.leetcode_service = mock_leetcode_service

    # Act
    result = await analytics_service.sync_user_submissions(
        user_id="test_user",
        username="test",
        csrf_token="token",
        cookie="cookie"
    )

    # Assert
    assert result is not None
    questions = result.progress_data.leetcode.questions
    assert len(questions) == 3
    solved = [q for q in questions if q.status == "solved"]
    attempted = [q for q in questions if q.status == "attempted"]
    assert len(solved) == 1
    assert len(attempted) == 2

@pytest.mark.asyncio
async def test_error_handling(mock_leetcode_service, mongodb):
    """Test error handling"""
    # Arrange
    mock_leetcode_service.fetch_all_submissions.side_effect = Exception("API Error")
    
    from leetcode_service import AnalyticsService
    analytics_service = AnalyticsService()
    analytics_service.leetcode_service = mock_leetcode_service

    # Act & Assert
    with pytest.raises(Exception) as exc_info:
        await analytics_service.sync_user_submissions(
            user_id="test_user",
            username="test",
            csrf_token="token",
            cookie="cookie"
        )
    assert str(exc_info.value) == "API Error"