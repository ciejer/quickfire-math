from __future__ import annotations
from typing import Optional
from datetime import datetime
from enum import Enum

from sqlmodel import SQLModel, Field


class DrillTypeEnum(str, Enum):
    addition = "addition"
    subtraction = "subtraction"
    multiplication = "multiplication"
    division = "division"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    display_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# NOTE: Settings are retained for backward compatibility but are no longer used for generation.
class UserSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")

    add_enabled: bool = True
    add_min: int = 0
    add_max: int = 12

    sub_enabled: bool = True
    sub_min: int = 0
    sub_max: int = 12

    mul_enabled: bool = True
    mul_a_min: int = 1
    mul_a_max: int = 12
    mul_b_min: int = 1
    mul_b_max: int = 12

    div_enabled: bool = True
    div_q_min: int = 1
    div_q_max: int = 12
    div_divisor_min: int = 1
    div_divisor_max: int = 12


class DrillResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    drill_type: DrillTypeEnum
    settings_snapshot: str  # now: level label + summary
    question_count: int = 20
    elapsed_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DrillQuestion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    drill_result_id: int = Field(foreign_key="drillresult.id")
    drill_type: DrillTypeEnum
    a: int
    b: int
    prompt: str
    correct_answer: int
    given_answer: int
    correct: bool  # whether THIS attempt was correct
    started_at: datetime
    elapsed_ms: int  # ms for this attempt


class AdminConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    admin_password_plain: str


# NEW: per-user/type progress
class UserProgress(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    drill_type: DrillTypeEnum
    level: int = 1
    ewma_tpq_ms: Optional[float] = None  # avg time per first-try correct question
    ewma_acc: Optional[float] = None     # 0..1, first-try accuracy
    stars_recent: str = ""               # e.g. "10101" (latest at end)
    best_time_ms: Optional[int] = None   # best total time for THIS level & type
    best_acc: Optional[float] = None     # best ACC for THIS level & type
    last_levelup_at: Optional[datetime] = None


# NEW: awards attached to a DrillResult
class DrillAward(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    drill_result_id: int = Field(foreign_key="drillresult.id")
    award_type: str   # 'star','pb_time','pb_acc','level_up'
    payload: str      # human text
