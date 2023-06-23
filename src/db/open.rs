use log::info;
use crate::WorkingDirectory;

pub fn open_db(wd: &WorkingDirectory) -> rusqlite::Result<rusqlite::Connection> {
    let path = &wd.path.join("hattivatti.db");
    if !path.exists() { info!("Creating new database {}", path.display()) }
    let conn = rusqlite::Connection::open(&path)?;

    static SCHEMA: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/db/schema.sql"));
    conn.execute(SCHEMA, [], )?;

    info!("Creating dry run save point");
    conn.execute("SAVEPOINT dry_run", []).expect("Start transaction");

    Ok(conn)
}
