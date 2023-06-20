use std::path::Path;

use anyhow::Result;
use rusqlite::{Connection, OpenFlags};

pub fn open_db(path: &Path) -> Result<Connection> {
    // open flags changed to error if database doesn't exist
    let db = Connection::open_with_flags(path,
                                         OpenFlags::SQLITE_OPEN_READ_WRITE
                                             | OpenFlags::SQLITE_OPEN_URI
                                             | OpenFlags::SQLITE_OPEN_NO_MUTEX)?;
    return Ok(db);
}

