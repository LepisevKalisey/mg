-- Database schema generated from Alembic migrations

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS secrets (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    enc_value BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS master_sessions (
    id SERIAL PRIMARY KEY,
    enc_session BYTEA NOT NULL,
    valid BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sources (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT NOT NULL,
    username TEXT,
    title TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    trust_level INT,
    added_by BIGINT,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_posts (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id),
    tg_message_id BIGINT NOT NULL,
    author TEXT,
    text TEXT,
    media JSONB,
    urls TEXT[],
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    simhash BIGINT,
    status TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_posts_source_msg ON raw_posts (source_id, tg_message_id);

CREATE TABLE IF NOT EXISTS topics (
    id BIGSERIAL PRIMARY KEY,
    raw_post_id BIGINT NOT NULL REFERENCES raw_posts(id),
    ordinal INT,
    text TEXT,
    urls TEXT[],
    status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_topics_raw_post_id ON topics (raw_post_id);

CREATE TABLE IF NOT EXISTS summaries (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id),
    prompt_version INT,
    model TEXT,
    summary_text TEXT,
    citations TEXT[],
    tokens_in INT,
    tokens_out INT,
    cost_cents INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_summaries_topic_id ON summaries (topic_id);

CREATE TABLE IF NOT EXISTS digests (
    id BIGSERIAL PRIMARY KEY,
    scheduled_at TIMESTAMPTZ NOT NULL,
    posted_at TIMESTAMPTZ,
    target_channel_id BIGINT,
    status TEXT
);

CREATE INDEX IF NOT EXISTS ix_digests_scheduled_at ON digests (scheduled_at);

CREATE TABLE IF NOT EXISTS digest_items (
    digest_id BIGINT NOT NULL REFERENCES digests(id),
    summary_id BIGINT NOT NULL REFERENCES summaries(id),
    position INT,
    PRIMARY KEY (digest_id, summary_id)
);

