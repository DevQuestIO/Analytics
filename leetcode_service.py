from typing import Optional, Dict, List, Tuple
import httpx
import asyncio
from datetime import datetime, timedelta
from models import UserProgress, Question, PlatformProgress, AggregatedStats, ProgressData, TagStats, TagStat, ProblemCounts, LanguageStat
from leetcode_graphql import LeetCodeGraphQLService
from pydantic import BaseModel
import backoff
import logging
from redis_service import RedisService
import os
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

class LeetCodeSubmission(BaseModel):
    id: int
    question_id: int
    title: str
    title_slug: str
    status_display: str
    timestamp: int
    runtime: str
    memory: str
    lang: str

class LeetCodeService:
    def __init__(self):
        self.logger = logging.getLogger('devquest.leetcode')
        self.base_url = "https://leetcode.com/api"
        self.submission_url = f"{self.base_url}/submissions/"
        
    async def _make_request(self, url: str, headers: Dict[str, str], params: Dict[str, str]) -> Dict:
        @backoff.on_exception(
            backoff.expo,
            (httpx.HTTPError, httpx.TimeoutException),
            max_tries=3
        )
        async def _fetch():
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
        
        return await _fetch()

    async def fetch_all_submissions(
        self,
        csrf_token: str,
        cookie: str,
        last_sync_timestamp: Optional[datetime] = None
    ) -> List[LeetCodeSubmission]:
        self.logger.info(f"Starting to fetch submissions with timestamp > {last_sync_timestamp}")
        headers = {
            "x-csrftoken": csrf_token,  # Changed from X-CSRFToken to x-csrftoken
            "Cookie": cookie,
            "User-Agent": "DevQuest.IO Analytics Service",
            "Referer": "https://leetcode.com"  # Adding Referer header as it's often required
        }
        self.logger.debug(f"Request headers (masked): {{'x-csrftoken': '***', 'Cookie': '***', 'User-Agent': '{headers['User-Agent']}'}}")
        
        all_submissions = []
        offset = 0
        last_key = ""
        
        while True:
            params = {"offset": offset, "limit": 20}
            if last_key:
                params["lastkey"] = last_key
            
            self.logger.debug(f"Making request with params: {params}")
            
            try:
                response = await self._make_request(
                    self.submission_url,
                    headers=headers,
                    params=params
                )
                
                submissions = response.get("submissions_dump", [])
                self.logger.info(f"Fetched {len(submissions)} submissions for offset {offset}")
                # logger.info(submissions, "submissions hereee")
                if not submissions:
                    self.logger.info("No more submissions to fetch")
                    break
                
                if last_sync_timestamp:
                    original_count = len(submissions)
                    submissions = [
                        sub for sub in submissions 
                        if datetime.fromtimestamp(sub["timestamp"]) > last_sync_timestamp
                    ]
                    # datetime.fromtimestamp(submission.timestamp)
                    self.logger.debug(f"Filtered {original_count - len(submissions)} old submissions")
                    if not submissions:
                        self.logger.info("All remaining submissions are older than last sync")
                        break
                
                all_submissions.extend(submissions)
                
                if not response.get("has_next"):
                    self.logger.info("No more pages to fetch")
                    break
                
                last_key = response.get("last_key", "")
                offset += 20
                
                self.logger.debug(f"Moving to next page with offset {offset}")
                await asyncio.sleep(2)
                
            except Exception as e:
                self.logger.error(f"Error fetching submissions: {str(e)}", exc_info=True)
                break
        
        self.logger.info(f"Successfully fetched total {len(all_submissions)} submissions")
        return [LeetCodeSubmission(**sub) for sub in all_submissions]

    @staticmethod
    def _get_difficulty(question_id: int) -> str:
        return "medium"  # Default to medium for now

    @staticmethod
    def _get_topics(question_id: int) -> List[str]:
        return ["algorithms"]  # Default topic

class AnalyticsService:
    def __init__(self):
        self.logger = logging.getLogger('devquest.analytics')
        self.leetcode_service = LeetCodeService()
        self.graphql_service = LeetCodeGraphQLService()
        self.redis_service = RedisService(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    
    def process_problem_stats(self, stats_data: Dict) -> ProblemCounts:
        """Process problem statistics into ProblemCounts model"""
        if not stats_data:
            return ProblemCounts(
                total={},
                solved={},
                beats={}
            )

        # Process total counts
        total_counts = {
            item["difficulty"]: item["count"]
            for item in stats_data.get("allQuestionsCount", [])
        }

        # Process solved counts
        solved_counts = {
            item["difficulty"]: item["count"]
            for item in stats_data.get("matchedUser", {})
                .get("submitStatsGlobal", {})
                .get("acSubmissionNum", [])
        }

        # Process beats stats
        beats_stats = {
            item["difficulty"]: item["percentage"]
            for item in stats_data.get("matchedUser", {})
                .get("problemsSolvedBeatsStats", [])
        }

        return ProblemCounts(
            total=total_counts,
            solved=solved_counts,
            beats=beats_stats
        )

    async def sync_user_submissions(
        self,
        user_id: str,
        csrf_token: str,
        username: str,
        cookie: str
    ) -> UserProgress:
        self.logger.info(f"Starting sync for user: {user_id}")

        # Get or create user progress
        user_progress = await UserProgress.find_one({"user_id": user_id})
        if not user_progress:
            user_progress = UserProgress(
                user_id=user_id,
                progress_data=ProgressData(
                    leetcode=PlatformProgress(questions=[]),
                    geeksforgeeks=None
                ),
                aggregated_stats=AggregatedStats()
            )
        
        last_sync_timestamp = user_progress.progress_data.leetcode.questions[0].last_attempted if len(user_progress.progress_data.leetcode.questions) > 0 else None
        
        # Create tasks for parallel execution
        submissions_task = self.leetcode_service.fetch_all_submissions(
            csrf_token,
            cookie,
            last_sync_timestamp=last_sync_timestamp
        )
        
        stats_task = self.graphql_service.fetch_all_stats(
            username,
            csrf_token,
            cookie
        )
        
        submissions, (
            tag_stats,
            language_stats,
            problem_stats,
            calendar_data,
            badge_data
        ) = await asyncio.gather(
            submissions_task,
            stats_task
        )
        
        self.logger.info(f"Fetched all data for user {user_id}")

        questions_map = {}
        for submission in submissions:
            question_id = str(submission.question_id)
            
            if question_id in questions_map:
                continue
                
            self.logger.debug(f"Processing submission for question {submission.title}")
            questions_map[question_id] = Question(
                id=question_id,
                name=submission.title,
                difficulty=self.leetcode_service._get_difficulty(submission.question_id),
                topics=self.leetcode_service._get_topics(submission.question_id),
                status="solved" if submission.status_display == "Accepted" else "attempted",
                attempts=1,
                time_spent=0,
                last_attempted=datetime.fromtimestamp(submission.timestamp)
            )

        if user_progress.progress_data.leetcode is None:
            self.logger.info("Initializing LeetCode progress data")
            user_progress.progress_data.leetcode = PlatformProgress(questions=[])
            
        existing_questions = {
            q.id: q for q in user_progress.progress_data.leetcode.questions
        }
        new_questions = []
        
        for qid, question in questions_map.items():
            if qid in existing_questions:
                self.logger.debug(f"Updating existing question {qid}")
                existing = existing_questions[qid]
                existing.status = question.status
                existing.last_attempted = question.last_attempted
                # existing.attempts += 1
            else:
                self.logger.debug(f"Adding new question {qid}")
                new_questions.append(question)
                # user_progress.progress_data.leetcode.questions.append(question)

        user_progress.progress_data.leetcode.questions = new_questions + list(existing_questions.values())
        self.logger.info("Updating user statistics")
        user_progress.last_updated = datetime.utcnow()

        if tag_stats:
            user_progress.aggregated_stats.tag_stats = TagStats(
                advanced=[
                    TagStat(**tag) for tag in tag_stats.get("advanced", [])
                ],
                intermediate=[
                    TagStat(**tag) for tag in tag_stats.get("intermediate", [])
                ],
                fundamental=[
                    TagStat(**tag) for tag in tag_stats.get("fundamental", [])
                ]
            )
            
            # Update by_topic with combined stats
            topic_counts = {}
            for category in ["advanced", "intermediate", "fundamental"]:
                for tag in tag_stats.get(category, []):
                    topic_counts[tag["tagSlug"]] = tag["problemsSolved"]
            
            user_progress.aggregated_stats.by_topic = topic_counts
        
        if language_stats:
            user_progress.aggregated_stats.by_language = [
                LanguageStat(**lang) for lang in language_stats
            ]

        # Update problem stats
        if problem_stats:
            user_progress.aggregated_stats.problem_counts = self.process_problem_stats(problem_stats)
            total_solved = user_progress.aggregated_stats.problem_counts.solved.get('All')
            user_progress.aggregated_stats.total_solved = total_solved
        
        if calendar_data:
            user_progress.aggregated_stats.calendar_stats = (
                self.graphql_service.process_calendar_data(calendar_data)
            )
        
        if badge_data:
            user_progress.aggregated_stats.badges = (
                self.graphql_service.process_badge_data(badge_data)
            )

        self.logger.info("Saving progress to MongoDB")
        try:
            await user_progress.save()
            self.logger.info("Successfully saved user progress to mongodb")
            await self.redis_service.store_aggregated_stats(
                user_id,
                user_progress.aggregated_stats.dict()
            )
            self.logger.info("Successfully saved user progress to redis")
        except Exception as e:
            self.logger.error(f"Failed to save user progress: {str(e)}", exc_info=True)
            raise
            
        return user_progress

    def calculate_submission_intensity(self, count: int) -> int:
        """Calculate color intensity based on submission count"""
        if count == 0:
            return 0
        elif count <= 3:
            return 1
        elif count <= 6:
            return 2
        elif count <= 10:
            return 3
        else:
            return 4  # Maximum intensity

    async def get_calendar_heatmap(
        self,
        user_id: str,
        year: Optional[int] = None
    ) -> Dict:
        """Get calendar heatmap data for visualization"""
        user_progress = await UserProgress.find_one({"user_id": user_id})
        if not user_progress or not user_progress.aggregated_stats.calendar_stats:
            return {}

        calendar_stats = user_progress.aggregated_stats.calendar_stats
        year = year or datetime.now().year

        # Create full year data with intensity levels
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)
        current_date = start_date

        heatmap_data = {}
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            count = calendar_stats.submissions_by_date.get(date_str, 0)
            intensity = self.calculate_submission_intensity(count)
            
            heatmap_data[date_str] = {
                "count": count,
                "intensity": intensity
            }
            
            current_date = current_date + timedelta(days=1)

        return {
            "heatmap": heatmap_data,
            "stats": {
                "total_submissions": sum(calendar_stats.submissions_by_date.values()),
                "active_days": calendar_stats.total_active_days,
                "current_streak": calendar_stats.streak,
                "monthly_totals": calendar_stats.monthly_submissions,
                "yearly_totals": calendar_stats.yearly_submissions
            }
        }
