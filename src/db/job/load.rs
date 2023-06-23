use log::info;
use rusqlite::Connection;
use serde_json::Result as JsonResult;

use crate::slurm::job_request::JobRequest;

pub fn get_valid_jobs(conn: &Connection, dry_run: bool) -> Option<Vec<JobRequest>> {
    let mut stmt = conn.prepare("SELECT manifest FROM job WHERE valid == 1 AND staged == 0 AND submitted == 0").expect("");
    let rows = stmt.query_map([], |row| row.get(0)).expect("");

    let mut json: Vec<String> = Vec::new();
    for row in rows {
        let json_string: String = row.expect("");
        info!("Loading valid job from db: {} ...", &json_string[..50]);
        json.push(json_string);
    }

    release_or_rollback(&conn, dry_run);

    let jobs = deserialise(json).expect("Deserialised JSON");
    match jobs.is_empty() {
        true => { None }
        false => { Some(jobs) }
    }
}

fn deserialise(json_strings: Vec<String>) -> JsonResult<Vec<JobRequest>> {
    let mut jobs: Vec<JobRequest> = Vec::new();
    for string in json_strings {
        let job: JobRequest = serde_json::from_str(&string)?;
        jobs.push(job);
    }
    Ok(jobs)
}

fn release_or_rollback(conn: &Connection, dry_run: bool) {
    match dry_run {
        true => {
            info!("--dry-run set, rolling back database state");
            conn.execute("ROLLBACK TO dry_run", []).expect("rollback");
        }
        false => {
            info!("--dry-run not set, releasing dry run save point");
            conn.execute("RELEASE dry_run", []).expect("release");
        }
    }
}