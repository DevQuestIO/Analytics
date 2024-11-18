# leetcode_graphql.py
import httpx
import logging
from typing import Dict, Optional
import json

logger = logging.getLogger('devquest.leetcode.graphql')

class LeetCodeGraphQLService:
    def __init__(self):
        self.graphql_url = "https://leetcode.com/graphql/"
        
    async def fetch_user_tag_stats(self, username: str, csrf_token: str, cookie: str) -> Optional[Dict]:
        """Fetch user's tag statistics from LeetCode GraphQL API"""
        query = """
        query skillStats($username: String!) {
          matchedUser(username: $username) {
            tagProblemCounts {
              advanced {
                tagName
                tagSlug
                problemsSolved
              }
              intermediate {
                tagName
                tagSlug
                problemsSolved
              }
              fundamental {
                tagName
                tagSlug
                problemsSolved
              }
            }
          }
        }
        """
        
        variables = {"username": username}
        
        headers = {
            "Content-Type": "application/json",
            "x-csrftoken": csrf_token,
            "Cookie": cookie,
            "Referer": "https://leetcode.com"
        }
        
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
                    
                return data.get("data", {}).get("matchedUser", {}).get("tagProblemCounts", {})
                
        except Exception as e:
            logger.error(f"Failed to fetch tag stats: {str(e)}", exc_info=True)
            return None