CREATE TABLE IF NOT EXISTS public.quiz_results (
    submission_id uuid PRIMARY KEY,
    participant_name text NOT NULL CHECK (length(trim(participant_name)) > 0),
    participant_affiliation text NOT NULL CHECK (length(trim(participant_affiliation)) > 0),
    product text NOT NULL,
    question_bank_version integer NOT NULL,
    total_questions integer NOT NULL CHECK (total_questions > 0),
    correct_count integer NOT NULL CHECK (correct_count BETWEEN 0 AND total_questions),
    total_points integer NOT NULL CHECK (total_points >= 0),
    answers jsonb NOT NULL CHECK (
        jsonb_typeof(answers) = 'array'
        AND jsonb_array_length(answers) = total_questions
    ),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL CHECK (completed_at >= started_at),
    consent_at timestamptz NOT NULL,
    consent_version text NOT NULL,
    is_test_data boolean NOT NULL DEFAULT TRUE CHECK (is_test_data)
);

ALTER TABLE public.quiz_results ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.quiz_results FROM PUBLIC, anon, authenticated;
