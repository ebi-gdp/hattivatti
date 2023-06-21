use std::{fs, io};
use std::path::Path;
use log::{info, warn};
use rusqlite::Connection;
use crate::request::job::JobRequest;
use anyhow::Result;

// once a message is read, start
pub fn add_job(conn: &Connection, job: Result<(), io::Error>, path: &Path) -> Result<()> {
    info!("Adding job to db");
    // read raw message content again to store in db
    let json: String = fs::read_to_string(path)?;
    let valid: bool = job.is_ok();
    let is_submitted: bool = false;

    conn.execute(
        "INSERT INTO job (manifest, valid, submitted) VALUES (?1, ?2, ?3)",
        (json, valid, is_submitted)
    )?;

    cleanup_manifest(path);

    Ok(())
}

// once committed the the database, the original manifest is deleted
fn cleanup_manifest(path: &Path) {
    match fs::remove_file(path) {
        Ok(()) => info!("{} deleted", path.display()),
        Err(err) => warn!("Couldn't delete {}, {}", path.display(), err)
    }
}
