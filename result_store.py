from datetime import datetime
from typing import TypedDict
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


TEST_CONSENT_VERSION = "test-cloud-v1"


class DatabaseSettings(TypedDict):
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str


class QuizSubmission(TypedDict):
    submission_id: UUID
    participant_name: str
    participant_affiliation: str
    product: str
    question_bank_version: int
    total_questions: int
    correct_count: int
    total_points: int
    answers: list[dict[str, object]]
    started_at: datetime
    completed_at: datetime
    consent_at: datetime
    consent_version: str


def save_submission(settings: DatabaseSettings, submission: QuizSubmission) -> None:
    with psycopg.connect(
        **settings, connect_timeout=10, options="-c statement_timeout=15000"
    ) as connection:
        connection.execute(
            """
            INSERT INTO public.quiz_results (
                submission_id, participant_name, participant_affiliation, product,
                question_bank_version, total_questions, correct_count, total_points,
                answers, started_at, completed_at, consent_at, consent_version,
                is_test_data
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE
            )
            ON CONFLICT (submission_id) DO NOTHING
            """,
            (
                submission["submission_id"],
                submission["participant_name"],
                submission["participant_affiliation"],
                submission["product"],
                submission["question_bank_version"],
                submission["total_questions"],
                submission["correct_count"],
                submission["total_points"],
                Jsonb(submission["answers"]),
                submission["started_at"],
                submission["completed_at"],
                submission["consent_at"],
                submission["consent_version"],
            ),
        )
