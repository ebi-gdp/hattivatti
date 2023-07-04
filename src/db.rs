//! All job state is stored in a SQLite database

/// Connect to a SQLite database
pub mod open;
pub mod job;
/// Stream and validate job request messages
pub mod ingest;