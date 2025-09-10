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


class UserSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")

    # Addition/Subtraction symmetric bounds
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

    # Division (new: quotient min/max + divisor min/max)
    div_enabled: bool = True
    div_q_min: int = 1
    div_q_max: int = 12
    div_divisor_min: int = 1
    div_divisor_max: int = 12


class DrillResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    drill_type: DrillTypeEnum
    settings_snapshot: str
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
    correct: bool
    started_at: datetime
    elapsed_ms: int


class AdminConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    admin_password_plain: str  # printed to logs on boot (per spec)


class MinExpectations(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")

    # Addition/Subtraction: required inclusion range
    add_req_min: int = 0
    add_req_max: int = 10
    sub_req_min: int = 0
    sub_req_max: int = 10

    # Multiplication: both factor ranges must include these
    mul_a_req_min: int = 1
    mul_a_req_max: int = 7
    mul_b_req_min: int = 1
    mul_b_req_max: int = 7

    # Division: we can extend later if you want reqs for quotient/divisor too
