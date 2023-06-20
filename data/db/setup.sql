CREATE TABLE IF NOT EXISTS job (
    job_id INTEGER PRIMARY KEY,
    intervene_id TEXT AS (json_extract(Manifest, '$.pipeline_param.id')) UNIQUE,
    manifest TEXT,
    valid INTEGER,
    valid_status TEXT,
    submitted INTEGER,
    created_at TEXT
);
