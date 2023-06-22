use std::{fs, io};
use std::path::{Path, PathBuf};

use clap::Parser;
use log::info;
use rusqlite::Connection;

use crate::db::load::message::load_message;
use crate::db::submit::load::get_valid_jobs;
use crate::request::message::Message;
use crate::slurm::job::create_job;

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
    #[arg(short, long)]
    schema_dir: PathBuf,
    #[arg(short, long)]
    message_dir: PathBuf,
    #[arg(short, long)]
    db_path: String,
    #[arg(short, long)]
    work_dir: PathBuf
}

pub struct WorkingDirectory { path: PathBuf }

fn main() {
    env_logger::init();
    info!("terve! starting up :)");

    let args = Args::parse();
    let wd = WorkingDirectory { path: args.work_dir };
    fs::create_dir_all(&wd.path).expect("Can't create working directory");

    let conn: Connection = db::open::open_db(Path::new(&args.db_path))
        .expect("Database connection");

    let schema = request::schema::load_schema(args.schema_dir.as_path());

    let messages: Result<Vec<Message>, io::Error> = request::message::from_dir(args.message_dir.as_path());

    for message in messages.unwrap() {
        let job: Result<(), io::Error> = message.read(&schema);
        let _ = load_message(&conn, job, message.path.as_path());
    }

    let jobs = get_valid_jobs(&conn).unwrap();
    info!("{:?}", jobs);

    for job in jobs {
        let _ = create_job(job, &wd);
    }


    //let x = m.read();
    //println!("Valid serde? {:?}", x.is_ok());


    info!("hattivatti finished")
}
