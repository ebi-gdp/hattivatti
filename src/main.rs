use std::fs;
use std::path::{Path, PathBuf};

use log::{info, warn};
use serde::{Deserialize, Serialize};
use serde_json::json;

use clap::Parser;
use rusqlite::{Connection, OpenFlags};
use crate::request::message::{JobRequest, Message};
use anyhow::Result;

mod db;
mod request;

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
    db_path: String
}

fn main() {
    env_logger::init();
    info!("terve! starting up :)");

    let args = Args::parse();

    let conn = db::open::open_db(Path::new( &args.db_path))
        .expect("Database connection");

    let schema = request::schema::load_schema(args.schema_dir.as_path());

    let messages: Result<Vec<Message>> = request::message::from_dir(args.message_dir.as_path());

    let mut list: Vec<JobRequest> = Vec::new();

    for message in messages.unwrap() {
        let x: JobRequest = message.read(&schema).unwrap();
        info!("{:#?}", x.pipeline_param);
    }


    //let x = m.read();
    //println!("Valid serde? {:?}", x.is_ok());


    info!("hattivatti finished")
}
