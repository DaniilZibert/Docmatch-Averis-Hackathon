-- OWNER: Person B. Starting schema for the service layer.
-- Adjust freely — nothing else in the repo depends on these tables yet.

CREATE TABLE IF NOT EXISTS emails (
    email_id    TEXT PRIMARY KEY,
    sender      TEXT,
    subject     TEXT,
    body        TEXT,
    attachments JSONB NOT NULL DEFAULT '[]',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per attachment we managed to read (SI or BL of an email).
CREATE TABLE IF NOT EXISTS extracted_documents (
    id           BIGSERIAL PRIMARY KEY,
    email_id     TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    doc_type     TEXT NOT NULL CHECK (doc_type IN ('SI', 'BL', 'UNKNOWN')),
    source_path  TEXT,
    fields       JSONB NOT NULL DEFAULT '{}',   -- {field: {value, confidence, source, raw_label}}
    unreadable   BOOLEAN NOT NULL DEFAULT FALSE,
    wrong_doc_type BOOLEAN NOT NULL DEFAULT FALSE,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (email_id, doc_type)
);

-- The verdict per email — this is what submission.json is built from.
CREATE TABLE IF NOT EXISTS results (
    email_id      TEXT PRIMARY KEY REFERENCES emails(email_id) ON DELETE CASCADE,
    category      TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('OK', 'MISMATCH', 'NEEDS_REVIEW')),
    review_reason TEXT,
    has_defect    BOOLEAN NOT NULL DEFAULT FALSE,
    defect_fields JSONB NOT NULL DEFAULT '[]',
    decided_by    TEXT,
    comparisons   JSONB NOT NULL DEFAULT '[]',  -- the 7 side-by-side rows
    error         TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Human-in-the-loop queue: everything the pipeline refused to decide.
CREATE TABLE IF NOT EXISTS review_queue (
    email_id     TEXT PRIMARY KEY REFERENCES emails(email_id) ON DELETE CASCADE,
    reason       TEXT NOT NULL,
    evidence     JSONB NOT NULL DEFAULT '{}',   -- extracted values + raw labels, for the screen
    resolved     BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by  TEXT,
    resolution   JSONB,                          -- the corrected verdict a human entered
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS review_queue_open_idx ON review_queue (resolved) WHERE resolved = FALSE;
CREATE INDEX IF NOT EXISTS results_status_idx ON results (status);
