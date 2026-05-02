from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=6, max_length=200)
    role: Literal["student", "instructor"]
    email: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class GenerateExamRequest(BaseModel):
    topic: str
    difficulty: str = "Beginner"
    mcq_count: int = Field(default=3, ge=1, le=20)
    essay_count: int = Field(default=2, ge=0, le=10)


class GenerateExamFromPdfRequest(BaseModel):
    pdf_name: str
    topic: str | None = None
    difficulty: str = "Beginner"
    mcq_count: int = Field(default=3, ge=1, le=20)
    essay_count: int = Field(default=2, ge=0, le=10)


class PracticeExamRequest(BaseModel):
    instructor_id: int
    topic: str = "Practice Exam"
    difficulty: str = "Beginner"
    mcq_count: int = Field(default=3, ge=1, le=20)
    essay_count: int = Field(default=1, ge=0, le=10)
    status: Literal["draft", "published"] = "published"


class CreateExamRequest(BaseModel):
    instructor_id: int
    topic: str
    difficulty: str = "Beginner"
    content: str
    status: Literal["draft", "published", "archived"] = "draft"
    rubric: str | None = None
    due_at: datetime | None = None
    source_refs: list[str] = Field(default_factory=list)


class UpdateExamRequest(BaseModel):
    instructor_id: int
    status: Literal["draft", "published", "archived"]
    due_at: datetime | None = None
    rubric: str | None = None


class SubmitRequest(BaseModel):
    exam_id: int
    student_id: int
    answers: dict[str, Any] | str
    proctor_session_id: str | None = None


class GradeRequest(BaseModel):
    submission_id: int
    instructor_id: int


class ManualOverrideRequest(BaseModel):
    instructor_id: int
    score: int = Field(ge=0, le=100)
    note: str | None = None


class ProctorStartRequest(BaseModel):
    student_id: int
    exam_id: int
    duration_min: int = Field(ge=1, le=360)
    student_name: str = Field(min_length=1, max_length=200)
    exam_title: str = Field(min_length=1, max_length=300)


class ProctorFrameRequest(BaseModel):
    image_base64: str = Field(min_length=10)


class ProctorEndRequest(BaseModel):
    invalidate_reason: str | None = None


class ProctorInvalidateRequest(BaseModel):
    instructor_id: int
    reason: str | None = None
