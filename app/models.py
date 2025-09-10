from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


class User(SQLModel, table=True):
    """Represents a player of the math drills."""

    id: Optional[int] = Field(default=None, primary_key=True)
    display_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # relationships
    settings: "UserSettings" = Relationship(back_populates="user")
    drills: list["DrillResult"] = Relationship(back_populates="user")


class UserSettings(SQLModel, table=True):
    """Stores per‑user preferences for each drill type."""

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
    div_enabled: bool = True
    div_dividend_max: int = 144
    div_divisor_min: int = 1
    div_divisor_max: int = 12

    user: User = Relationship(back_populates="settings")


DrillType = Literal["addition", "subtraction", "multiplication", "division"]


class DrillResult(SQLModel, table=True):
    """Persisted history for completed drills."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    drill_type: DrillType
    # store settings snapshot for the newsfeed
    settings_snapshot: str  # human-friendly summary
    question_count: int = 20
    elapsed_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user: User = Relationship(back_populates="drills")