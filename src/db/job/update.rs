use std::path::Path;
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
        self.update(conn, state);
        self.update_slurm(conn, job_id).expect("update OK");
    }

    fn update_slurm(&self, conn: &Connection, slurm_id: String) -> rusqlite::Result<()> {
        let id = &self.pipeline_param.id.to_string();
        info!("Updating {id} with slurm ID {slurm_id}");
        conn
            .execute("UPDATE job SET slurm_id = ? WHERE intervene_id = ?",
            &[&slurm_id, &id])
            .expect("Update");

        Ok(())
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
        let output_path = wd.join(Path::new("%j.out"));
        let output_str = output_path.to_str().unwrap();
        info!("Output path: {output_str}");
        let job_script_path = job_path.path.to_str().unwrap();

        let arguments = vec!["--parsable", "--output", output_str, job_script_path];

        let mut sbatch = Command::new("sbatch");
        let cmd = sbatch.args(&arguments);
        info!("{:?}", &cmd);
        let output = cmd.output().expect("failed to execute process").stdout;

        String::from_utf8(output).expect("job id")
    }
}
