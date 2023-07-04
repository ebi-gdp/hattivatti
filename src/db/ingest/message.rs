use anyhow::Result;
use log::info;
use rusqlite::Connection;

use crate::request::message::AllasMessage;

/// Load an AllasMessage into a database
///
/// The AllasMessage is stored in a JSON column and the schema will automatically extract the
/// INTERVENE ID and add an insertion timestamp
pub fn ingest_message(conn: &Connection, message: &AllasMessage) -> Result<()> {
    info!("Adding {} to db", &message.key);
    let json = &message.content;
    let valid = &message.valid;

    conn.execute(
        "INSERT INTO job (manifest, valid) VALUES (?1, ?2)",
        (json, valid),
    )
        .expect("Error inserting job");

    Ok(())
}
