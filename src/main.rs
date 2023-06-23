use std::fs;
use std::path::{PathBuf};

use clap::Parser;
use log::info;
use rusqlite::Connection;

use crate::db::ingest::message::ingest_message;
use crate::db::job::load::get_valid_jobs;
use crate::slurm::job_request::JobRequest;

mod db;
mod request;
mod slurm;

#[derive(Parser, Debug)]
#[command(name = "hattivatti")]
#[command(author = "Benjamin Wingfield <bwingfield@ebi.ac.uk>")]
#[command(version = "0.1")]
#[command(about = "Submit pgsc_calc jobs to Puhti")]
#[command(long_about =
"This program reads job request messages from the INTERVENE backend and submits a sensitive data
processing task to the SLURM scheduler. The program also monitors the state of submitted jobs,
and notifies the INTERVENE backend when a requested job has succeeded or failed.")]
struct Args {
    /// A directory path that contains a set of JSON schema to validate messages in the job queue
    #[arg(short, long)]
    schema_dir: PathBuf,
    /// A directory where hattivatti can store jobs before submitting them to the SLURM scheduler
    #[arg(short, long)]
    work_dir: PathBuf,
    /// Read messages from the queue and create SLURM job files, but don't submit them to the SLURM scheduler
    #[arg(long)]
    dry_run: bool
}

pub struct WorkingDirectory {
    path: PathBuf,
}

#[tokio::main]
async fn main() {
    env_logger::init();
    info!("terve! starting up :)");

    let args = Args::parse();
    let wd = WorkingDirectory { path: args.work_dir };
    fs::create_dir_all(&wd.path).expect("Can't create working directory");

    let conn: Connection = db::open::open_db(&wd)
        .expect("Database connection");

    let schema = request::schema::load_schema(args.schema_dir.as_path());
    let s3_client = request::message::make_allas_client();
    let messages = request::message::fetch_all(&s3_client, &schema).await;

    if let Some(messages) = messages {
        for message in messages {
            // todo: check result of loading before deleting
            // todo: rollback insertions and updates with dry run
            // todo: prevent deletion with dry run
            let _ = ingest_message(&conn, &message);

            if !args.dry_run {
                message.delete(&s3_client).await;
            } else {
                info!("--dry-run set, not deleting message in queue");
            }
        }
    } else {
        info!("No new jobs in queue");
    }

    let jobs: Option<Vec<JobRequest>> = get_valid_jobs(&conn, args.dry_run);

    if let Some(jobs) = jobs {
        for job in jobs {
            job.create_job(&wd);
            if !args.dry_run {
                job.stage(&conn);
            } else {
                info!("--dry-run set, not submitting job to slurm");
            }
        }
    } else {
        info!("No jobs to load from database");
    }

    info!("finished :D")
}
