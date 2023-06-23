use log::info;
use rusqlite::Connection;

use crate::db::job::state::JobState;
use crate::slurm::job_request::JobRequest;

impl JobRequest {
    pub fn stage(&self, conn: &Connection) {
        let state = JobState::Staged;
        self.update(conn, state);
    }

    pub fn submit(&self, conn: &Connection) {
        let state = JobState::Submitted;
        self.update(conn, state);
    }

    fn update(&self, conn: &Connection, state: JobState) {
        let id = &self.pipeline_param.id.to_string();
        let col = state.to_string();
        info!("Updating {id} with state {col}");
        let stmt = format!("UPDATE job SET {col} = 1 WHERE intervene_id = (?1)");

        conn.execute(
            &stmt,
            &[(id.as_str())],
        ).expect("Update job status to {col}");
    }
}
