-- Data sources schema for supplementary financial report ingestion and retrieval.
-- Requires: pgvector extension.

CREATE SCHEMA IF NOT EXISTS data_sources;
CREATE EXTENSION IF NOT EXISTS vector;

-- Track each ingested report file
CREATE TABLE IF NOT EXISTS data_sources.report_documents (
    document_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_code       text NOT NULL,
    report_type     text NOT NULL,
    period_code     text NOT NULL,
    fiscal_year     int NOT NULL,
    fiscal_quarter  int NOT NULL,
    source_filename text NOT NULL,
    ingested_at     timestamptz DEFAULT now(),
    metadata        jsonb DEFAULT '{}',
    UNIQUE(bank_code, report_type, period_code)
);

-- One row per sheet: raw content + LLM-extracted index metadata
CREATE TABLE IF NOT EXISTS data_sources.report_sheets (
    sheet_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     uuid NOT NULL REFERENCES data_sources.report_documents(document_id),
    sheet_index     int NOT NULL,
    sheet_name      text NOT NULL,
    page_title      text,

    raw_content     text NOT NULL,

    summary         text,
    keywords        text[],

    summary_embedding vector(3072),

    context_sheet_ids uuid[],
    context_note    text,

    is_data_sheet   boolean DEFAULT true,
    metadata        jsonb DEFAULT '{}',

    UNIQUE(document_id, sheet_index)
);

-- Extracted metric+platform combos per sheet, each with its own embedding
CREATE TABLE IF NOT EXISTS data_sources.sheet_metrics (
    metric_id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sheet_id                uuid NOT NULL REFERENCES data_sources.report_sheets(sheet_id),
    metric_name             text NOT NULL,
    metric_name_normalized  text,
    platform                text,
    sub_platform            text,
    periods_available       text[],
    embedding               vector(3072),   -- embedding of "metric_name (platform / sub_platform)"
    metadata                jsonb DEFAULT '{}'
);

-- One embedding per keyword per sheet
CREATE TABLE IF NOT EXISTS data_sources.keyword_embeddings (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sheet_id    uuid NOT NULL REFERENCES data_sources.report_sheets(sheet_id),
    keyword     text NOT NULL,
    embedding   vector(3072)
);

-- Indexes for retrieval paths
CREATE INDEX IF NOT EXISTS idx_sheets_keywords
    ON data_sources.report_sheets USING gin (keywords);

CREATE INDEX IF NOT EXISTS idx_sheets_document
    ON data_sources.report_sheets (document_id);

CREATE INDEX IF NOT EXISTS idx_metrics_name_norm
    ON data_sources.sheet_metrics (metric_name_normalized);

CREATE INDEX IF NOT EXISTS idx_metrics_sheet
    ON data_sources.sheet_metrics (sheet_id);

CREATE INDEX IF NOT EXISTS idx_metrics_platform
    ON data_sources.sheet_metrics (platform);

CREATE INDEX IF NOT EXISTS idx_keyword_emb_sheet
    ON data_sources.keyword_embeddings (sheet_id);

-- IVFFlat index for semantic search (requires rows to exist before creation;
-- we create it conditionally via a DO block to handle first-time setup).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'idx_sheets_summary_embedding'
    ) THEN
        -- IVFFlat needs at least (lists * 39) rows to build.
        -- Use a low list count for small datasets; rebuild after large ingests.
        CREATE INDEX idx_sheets_summary_embedding
            ON data_sources.report_sheets
            USING ivfflat (summary_embedding vector_cosine_ops)
            WITH (lists = 10);
    END IF;
EXCEPTION
    WHEN others THEN
        -- If too few rows exist, IVFFlat creation fails; that's OK.
        -- The planner will fall back to sequential scan.
        RAISE NOTICE 'Skipping IVFFlat index creation: %', SQLERRM;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'idx_metrics_embedding'
    ) THEN
        CREATE INDEX idx_metrics_embedding
            ON data_sources.sheet_metrics
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 25);
    END IF;
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Skipping metric embedding IVFFlat index creation: %', SQLERRM;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'idx_keyword_embeddings_embedding'
    ) THEN
        CREATE INDEX idx_keyword_embeddings_embedding
            ON data_sources.keyword_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 25);
    END IF;
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Skipping keyword embedding IVFFlat index creation: %', SQLERRM;
END
$$;
