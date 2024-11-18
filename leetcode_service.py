from typing import Optional, Dict, List, Tuple
import httpx
import asyncio
from datetime import datetime
from models import UserProgress, Question, PlatformProgress, AggregatedStats, ProgressData, TagStats, TagStat
from leetcode_graphql import LeetCodeGraphQLService
from pydantic import BaseModel
import backoff
import logging
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
        last_sync_timestamp: Optional[int] = None
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
                        if sub["timestamp"] > last_sync_timestamp
                    ]
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

    async def sync_user_submissions(
        self,
        user_id: str,
        csrf_token: str,
        username: str,
        cookie: str
    ) -> UserProgress:
        self.logger.info(f"Starting sync for user: {user_id}")
        
        # Create tasks for parallel execution
        submissions_task = self.leetcode_service.fetch_all_submissions(
            csrf_token,
            cookie,
            last_sync_timestamp=None
        )
        
        tag_stats_task = self.graphql_service.fetch_user_tag_stats(
            username,
            csrf_token,
            cookie
        )
        
        # Execute tasks in parallel
        submissions, tag_stats = await asyncio.gather(
            submissions_task,
            tag_stats_task
        )
        
        self.logger.info(f"Fetched {len(submissions)} submissions and tag stats")
        
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
        
        for qid, question in questions_map.items():
            if qid in existing_questions:
                self.logger.debug(f"Updating existing question {qid}")
                existing = existing_questions[qid]
                existing.status = question.status
                existing.last_attempted = question.last_attempted
                existing.attempts += 1
            else:
                self.logger.debug(f"Adding new question {qid}")
                user_progress.progress_data.leetcode.questions.append(question)

        self.logger.info("Updating user statistics")
        total_solved = len([
            q for q in user_progress.progress_data.leetcode.questions
            if q.status == "solved"
        ])
        
        user_progress.aggregated_stats.total_solved = total_solved
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
        
        self.logger.info("Saving progress to MongoDB")
        try:
            await user_progress.save()
            self.logger.info("Successfully saved user progress")
        except Exception as e:
            self.logger.error(f"Failed to save user progress: {str(e)}", exc_info=True)
            raise
            
        return user_progress
