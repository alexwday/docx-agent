-- Postgres Schema V1 migration for docx-agent big upgrade.
-- This SQL is tooling-agnostic and can be applied with psql or wrapped by Alembic later.

begin;

create extension if not exists pgcrypto;

create table if not exists sessions (
    session_id uuid primary key default gen_random_uuid(),
    user_id char(9) not null check (user_id ~ '^[0-9]{9}$'),
    title text,
    status text not null default 'active' check (status in ('active', 'archived')),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_activity_at timestamptz not null default now()
);

create index if not exists idx_sessions_user_updated
    on sessions (user_id, updated_at desc);

create index if not exists idx_sessions_user_last_activity
    on sessions (user_id, last_activity_at desc);

create table if not exists session_messages (
    message_id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(session_id) on delete cascade,
    sequence_no bigint not null,
    role text not null check (role in ('user', 'assistant', 'system')),
    content_text text,
    content_json jsonb not null default '{}'::jsonb,
    parent_message_id uuid references session_messages(message_id),
    processing_state text not null default 'completed'
        check (processing_state in ('pending', 'completed', 'failed')),
    processing_started_at timestamptz,
    processing_ended_at timestamptz,
    error jsonb,
    created_at timestamptz not null default now(),
    unique (session_id, sequence_no),
    unique (session_id, message_id)
);

create index if not exists idx_session_messages_session_created
    on session_messages (session_id, created_at);

create index if not exists idx_session_messages_parent
    on session_messages (parent_message_id);

create index if not exists idx_session_messages_processing
    on session_messages (session_id, processing_state, created_at);

create table if not exists message_events (
    event_id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(session_id) on delete cascade,
    message_id uuid not null,
    event_index int not null,
    event_type text not null,
    payload jsonb not null,
    created_at timestamptz not null default now(),
    unique (message_id, event_index),
    constraint fk_message_events_session_message
        foreign key (session_id, message_id)
        references session_messages(session_id, message_id)
        on delete cascade
);

create index if not exists idx_message_events_session_created
    on message_events (session_id, created_at);

create index if not exists idx_message_events_type
    on message_events (event_type);

create table if not exists session_artifacts (
    artifact_id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(session_id) on delete cascade,
    artifact_group_id uuid,
    artifact_type text not null check (
        artifact_type in (
            'upload',
            'research_markdown',
            'research_output_doc',
            'report_working_doc',
            'report_final_doc',
            'export_file'
        )
    ),
    lifecycle_state text not null default 'final'
        check (lifecycle_state in ('draft', 'in_progress', 'final', 'superseded')),
    format text not null,
    filename text not null,
    storage_uri text not null,
    mime_type text,
    size_bytes bigint,
    checksum text,
    created_from_message_id uuid references session_messages(message_id) on delete set null,
    source_artifact_id uuid references session_artifacts(artifact_id) on delete set null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_session_artifacts_session_created
    on session_artifacts (session_id, created_at desc);

create index if not exists idx_session_artifacts_type
    on session_artifacts (artifact_type);

create index if not exists idx_session_artifacts_source
    on session_artifacts (source_artifact_id);

create index if not exists idx_session_artifacts_group
    on session_artifacts (artifact_group_id);

create index if not exists idx_session_artifacts_panes
    on session_artifacts (session_id, artifact_type, created_at desc);

create table if not exists artifact_knowledge_units (
    knowledge_id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(session_id) on delete cascade,
    artifact_id uuid not null references session_artifacts(artifact_id) on delete cascade,
    unit_type text not null check (unit_type in ('summary', 'chunk', 'table_extract')),
    sequence_no int not null default 0,
    content text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (artifact_id, unit_type, sequence_no)
);

create index if not exists idx_artifact_knowledge_session
    on artifact_knowledge_units (session_id, created_at);

create index if not exists idx_artifact_knowledge_artifact
    on artifact_knowledge_units (artifact_id, sequence_no);

create table if not exists data_source_catalog (
    source_id text primary key,
    name text not null,
    source_type text not null,
    location jsonb not null default '{}'::jsonb,
    schema_json jsonb not null default '{}'::jsonb,
    enabled boolean not null default true,
    updated_at timestamptz not null default now()
);

create index if not exists idx_data_source_catalog_enabled
    on data_source_catalog (enabled);

create index if not exists idx_data_source_catalog_type_enabled
    on data_source_catalog (source_type, enabled);

create or replace function set_row_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_sessions_set_updated_at on sessions;
create trigger trg_sessions_set_updated_at
before update on sessions
for each row
execute function set_row_updated_at();

create or replace function touch_session_activity_on_message_insert()
returns trigger
language plpgsql
as $$
begin
    update sessions
    set updated_at = now(),
        last_activity_at = now()
    where session_id = new.session_id;
    return new;
end;
$$;

drop trigger if exists trg_session_messages_touch_session on session_messages;
create trigger trg_session_messages_touch_session
after insert on session_messages
for each row
execute function touch_session_activity_on_message_insert();

commit;
