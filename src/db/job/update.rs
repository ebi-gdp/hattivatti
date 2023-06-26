use std::process::Command;
use log::info;
use rusqlite::Connection;

use crate::db::job::state::JobState;
use crate::slurm::job::JobPath;
use crate::slurm::job_request::JobRequest;

impl JobRequest {
    pub fn stage(&self, conn: &Connection) {
        let state = JobState::Staged;
        self.update(conn, state);
    }

    pub fn submit(&self, conn: &Connection, job: JobPath) {
        let job_id = self.run_sbatch(job);
        info!("SLURM job id: {job_id}");
        let state = JobState::Submitted;
        // todo: store SLURM job id in table too
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

    fn run_sbatch(&self, job_path: JobPath) -> String {
        let wd = job_path.path.parent().unwrap();
        let output = Command::new("sbatch")
            .arg("--parsable")
            .arg("--output")
            .arg(wd)
            .arg("--error")
            .arg(wd)
            .arg(job_path.path)
            .output()
            .expect("sbatch");

        String::from_utf8(output.stdout).expect("job id")
    }
}
