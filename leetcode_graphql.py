# leetcode_graphql.py
import httpx
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timezone
from models import CalendarStats, CalendarStreak, Badge
import json
import asyncio

logger = logging.getLogger('devquest.leetcode.graphql')

class LeetCodeGraphQLService:
    def __init__(self):
        self.graphql_url = "https://leetcode.com/graphql/"

    async def _make_graphql_request(
        self,
        query: str,
        variables: Dict,
        headers: Dict
    ) -> Optional[Dict]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.graphql_url,
                    json={
                        "query": query,
                        "variables": variables
                    },
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return None
                    
                return data.get("data", {})
        except Exception as e:
            logger.error(f"GraphQL request failed: {str(e)}", exc_info=True)
            return None

    async def fetch_user_tag_stats(
        self,
        username: str,
        csrf_token: str,
        cookie: str
    ) -> Optional[Dict]:
        """Fetch user's tag statistics"""
        query = """
        query skillStats($username: String!) {
          matchedUser(username: $username) {
            tagProblemCounts {
              advanced { tagName tagSlug problemsSolved }
              intermediate { tagName tagSlug problemsSolved }
              fundamental { tagName tagSlug problemsSolved }
            }
          }
        }
        """
        
        headers = {
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Cookie": cookie,
            "Referer": "https://leetcode.com"
        }
        
        data = await self._make_graphql_request(query, {"username": username}, headers)
        return data.get("matchedUser", {}).get("tagProblemCounts", {})

    async def fetch_calendar_stats(
        self,
        username: str,
        csrf_token: str,
        cookie: str
    ) -> Optional[Dict]:
        """Fetch user's submission calendar"""
        query = """
        query userProfileCalendar($username: String!, $year: Int) {
          matchedUser(username: $username) {
            userCalendar(year: $year) {
              activeYears
              streak
              totalActiveDays
              dccBadges {
                timestamp
                badge { name icon }
              }
              submissionCalendar
            }
          }
        }
        """
        
        headers = {
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Cookie": cookie,
            "Referer": "https://leetcode.com"
        }
        
        current_year = datetime.now().year
        data = await self._make_graphql_request(query, {
            "username": username,
            "year": current_year
        }, headers)
        
        return data.get("matchedUser", {}).get("userCalendar", {})

    def process_calendar_data(self, calendar_data: Dict) -> CalendarStats:
        """Process raw calendar data into structured format"""
        if not calendar_data:
            return CalendarStats()

        # Parse submission calendar
        submissions_calendar = json.loads(
            calendar_data.get("submissionCalendar", "{}")
        )

        # Convert Unix timestamps to YYYY-MM-DD format and organize data
        submissions_by_date = {}
        monthly_submissions = {}
        yearly_submissions = {}

        for timestamp_str, count in submissions_calendar.items():
            # Convert timestamp to datetime
            timestamp = int(timestamp_str)
            date = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            # Store daily data
            date_str = date.strftime("%Y-%m-%d")
            submissions_by_date[date_str] = count
            
            # Update monthly aggregates
            month_key = date.strftime("%Y-%m")
            monthly_submissions[month_key] = (
                monthly_submissions.get(month_key, 0) + count
            )
            
            # Update yearly aggregates
            year_key = date.strftime("%Y")
            yearly_submissions[year_key] = (
                yearly_submissions.get(year_key, 0) + count
            )

        return CalendarStats(
            active_years=calendar_data.get("activeYears", []),
            total_active_days=calendar_data.get("totalActiveDays", 0),
            streak=calendar_data.get("streak", 0),
            submissions_by_date=submissions_by_date,
            monthly_submissions=monthly_submissions,
            yearly_submissions=yearly_submissions,
            streaks=CalendarStreak(
                current=calendar_data.get("streak", 0),
                longest=calendar_data.get("streak", 0)  # You might want to calculate this separately
            )
        )


    async def fetch_language_stats(
        self,
        username: str,
        csrf_token: str,
        cookie: str
    ) -> Optional[List[Dict]]:
        """Fetch user's language statistics"""
        query = """
        query languageStats($username: String!) {
          matchedUser(username: $username) {
            languageProblemCount {
              languageName
              problemsSolved
            }
          }
        }
        """
        
        headers = {
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Cookie": cookie,
            "Referer": "https://leetcode.com"
        }
        
        data = await self._make_graphql_request(query, {"username": username}, headers)
        return data.get("matchedUser", {}).get("languageProblemCount", [])

    async def fetch_problem_stats(
        self,
        username: str,
        csrf_token: str,
        cookie: str
    ) -> Optional[Dict]:
        """Fetch user's problem solving statistics"""
        query = """
        query userProblemsSolved($username: String!) {
          allQuestionsCount {
            difficulty
            count
          }
          matchedUser(username: $username) {
            problemsSolvedBeatsStats {
              difficulty
              percentage
            }
            submitStatsGlobal {
              acSubmissionNum {
                difficulty
                count
              }
            }
          }
        }
        """
        
        headers = {
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Cookie": cookie,
            "Referer": "https://leetcode.com"
        }
        
        return await self._make_graphql_request(query, {"username": username}, headers)
    
    async def fetch_user_badges(
        self,
        username: str,
        csrf_token: str,
        cookie: str
    ) -> Optional[Dict]:
        """Fetch user's active badge"""
        query = """
        query getUserProfile($username: String!) {
          matchedUser(username: $username) {
            activeBadge {
              displayName
              icon
            }
          }
        }
        """
        
        headers = {
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Cookie": cookie,
            "Referer": "https://leetcode.com"
        }
        
        data = await self._make_graphql_request(query, {"username": username}, headers)
        return data.get("matchedUser", {}).get("activeBadge") if data else None

    def process_badge_data(self, badge_data: Optional[Dict]) -> List[Badge]:
        """Process badge data into structured format"""
        badges = []
        if badge_data:
            badges.append(Badge(
                display_name=badge_data.get("displayName", ""),
                icon_url=badge_data.get("icon", "")
            ))
        return badges

    async def fetch_all_stats(
        self,
        username: str,
        csrf_token: str,
        cookie: str
    ) -> Tuple[Optional[Dict], Optional[List[Dict]], Optional[Dict], Optional[Dict], Optional[Dict]]:
        """Fetch all statistics in parallel"""
        tag_stats_task = self.fetch_user_tag_stats(username, csrf_token, cookie)
        language_stats_task = self.fetch_language_stats(username, csrf_token, cookie)
        problem_stats_task = self.fetch_problem_stats(username, csrf_token, cookie)
        calendar_stats_task = self.fetch_calendar_stats(username, csrf_token, cookie)
        badge_stats_task = self.fetch_user_badges(username, csrf_token, cookie)
        
        results = await asyncio.gather(
            tag_stats_task,
            language_stats_task,
            problem_stats_task,
            calendar_stats_task,
            badge_stats_task,
            return_exceptions=True
        )
        
        return tuple(
            None if isinstance(result, Exception) else result
            for result in results
        )
