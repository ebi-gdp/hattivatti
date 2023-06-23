use rusqlite::Connection;

use crate::slurm::job_request::JobRequest;

impl JobRequest {
    pub fn stage(&self, conn: &Connection) {
        let id = &self.pipeline_param.id.to_string();
        conn.execute(
            "UPDATE job SET staged = 1 WHERE intervene_id = (?1)",
            &[(id.as_str())],
        ).expect("Update job status to staged");
    }
}
