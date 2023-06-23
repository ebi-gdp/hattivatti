CREATE TABLE IF NOT EXISTS job (
    job_id INTEGER PRIMARY KEY,
    intervene_id TEXT AS (json_extract(Manifest, '$.pipeline_param.id')) UNIQUE,
    manifest TEXT,
    valid INTEGER,
    staged INTEGER DEFAULT 0,
    submitted INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
