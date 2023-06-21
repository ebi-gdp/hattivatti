use log::info;
use rusqlite::Connection;
use serde_json::Result as JsonResult;
use crate::slurm::job_request::JobRequest;

pub fn get_valid_jobs(conn: &Connection) -> Result<Vec<JobRequest>, rusqlite::Error> {
    let mut stmt = conn.prepare("SELECT manifest FROM job WHERE valid == 1 AND submitted == 0")?;
    let rows = stmt.query_map([], |row| row.get(0))?;

    let mut json: Vec<String> = Vec::new();
    for row in rows {
        let json_string: String = row?;
        info!("Loading valid job from db: {} ...", &json_string[..50]);
        json.push(json_string);
    }

    let jobs = deserialise(json).expect("Deserialised JSON");
    Ok(jobs)
}

fn deserialise(json_strings: Vec<String>) -> JsonResult<Vec<JobRequest>> {
    let mut jobs: Vec<JobRequest> = Vec::new();
    for string in json_strings {
        let job: JobRequest = serde_json::from_str(&string)?;
        jobs.push(job);
    }
    Ok(jobs)
}