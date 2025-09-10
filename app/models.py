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
    # No ORM relationships needed for our usage (avoids SQLA typing issues)


class UserSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")

    # Addition/Subtraction share symmetric bounds
    add_enabled: bool = True
    add_min: int = 0
    add_max: int = 12

    sub_enabled: bool = True
    sub_min: int = 0
    sub_max: int = 12

    # Multiplication asymmetric
    mul_enabled: bool = True
    mul_a_min: int = 1
    mul_a_max: int = 12
    mul_b_min: int = 1
    mul_b_max: int = 12

    # Division (clean division): dividend_max, divisor_min/max
    # Keeping this schema (no migration). Defaults chosen to yield quotient ≈ 1–12.
    div_enabled: bool = True
    div_dividend_max: int = 144
    div_divisor_min: int = 1
    div_divisor_max: int = 12


class DrillResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    drill_type: DrillTypeEnum
    # Store settings snapshot + (now) appended score text
    settings_snapshot: str
    question_count: int = 20
    elapsed_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
