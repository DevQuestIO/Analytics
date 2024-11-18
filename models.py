from datetime import datetime
from typing import List, Dict, Optional
from beanie import Document, Indexed
from pydantic import BaseModel, Field

class Question(BaseModel):
    id: str
    name: str
    status: str
    last_attempted: datetime

class PlatformProgress(BaseModel):
    questions: List[Question]

class DifficultyStats(BaseModel):
    easy: int = 0
    medium: int = 0
    hard: int = 0

class TagStat(BaseModel):
    tagName: str
    tagSlug: str
    problemsSolved: int

class TagStats(BaseModel):
    advanced: List[TagStat] = Field(default_factory=list)
    intermediate: List[TagStat] = Field(default_factory=list)
    fundamental: List[TagStat] = Field(default_factory=list)

class ProgressData(BaseModel):
    leetcode: Optional[PlatformProgress]
    geeksforgeeks: Optional[PlatformProgress]

class UserProgress(Document):
    user_id: Indexed(str)
    progress_data: ProgressData
    aggregated_stats: AggregatedStats
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "user_progress"
        indexes = [
            [("user_id", 1)],
            [("aggregated_stats.total_solved", -1)]
        ]

class LanguageStat(BaseModel):
    languageName: str
    problemsSolved: int

class DifficultyCount(BaseModel):
    difficulty: str
    count: int

class DifficultyPercentage(BaseModel):
    difficulty: str
    percentage: Optional[float]

class GlobalSubmitStats(BaseModel):
    acSubmissionNum: List[DifficultyCount]

class ProblemCounts(BaseModel):
    total: Dict[str, int]  # e.g., {"All": 3353, "Easy": 835, ...}
    solved: Dict[str, int]  # e.g., {"All": 125, "Easy": 48, ...}
    beats: Dict[str, Optional[float]]  # e.g., {"Easy": 76.39, ...}

class AggregatedStats(BaseModel):
    total_solved: int = 0
    by_difficulty: Dict[str, int] = Field(default_factory=dict)
    by_topic: Dict[str, int] = Field(default_factory=dict)
    by_language: List[LanguageStat] = Field(default_factory=list)
    success_rate: float = 0.0
    tag_stats: Optional[TagStats] = None
    problem_counts: Optional[ProblemCounts] = None

