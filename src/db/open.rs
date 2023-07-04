use log::info;
use crate::WorkingDirectory;

/// Open a connection to an existing database, or create a new one if it doesn't exist
pub fn open_db(wd: &WorkingDirectory) -> rusqlite::Result<rusqlite::Connection> {
    let path = &wd.path.join("hattivatti.db");
    if !path.exists() { info!("Creating new database {}", path.display()) }
    let conn = rusqlite::Connection::open(&path)?;

    /// A SQLite database schema that stores job status
    static SCHEMA: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/db/schema.sql"));
    conn.execute(SCHEMA, [], )?;

    info!("Creating dry run save point");
    conn.execute("SAVEPOINT dry_run", []).expect("Start transaction");

    Ok(conn)
}
