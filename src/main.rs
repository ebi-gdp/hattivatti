use std::fs;
use std::path::{Path, PathBuf};

use log::{info, warn};
use serde::{Deserialize, Serialize};
use serde_json::{error, Result, Value};
use serde_json::json;

mod request;

use clap::Parser;
use crate::request::message::Message;

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
    message_dir: PathBuf
}

fn main() {
    env_logger::init();
    info!("terve! starting up :)");

    let args = Args::parse();

    let schema = request::schema::load_schema(args.schema_dir.as_path());

    let m: Message = Message {
        path: PathBuf::from(Path::new("/Users/bwingfield/Downloads/msgs/invalid_msg.json")),
        compiled_schema: schema
    };

    let x = m.read();
    println!("Valid serde? {:?}", x.is_some());


    // let valid_message = load_message(false);
    // let result = schema.validate(&valid_message);
    //
    // if let Err(errors) = result {
    //     for error in errors {
    //         warn!("Message fails validation");
    //         warn!("Validation error: {}", error);
    //         warn!("Instance path: {}", error.instance_path);
    //     }
    // } else {
    //     info!("Message passes validation")
    // }


    info!("hattivatti finished")
}

fn load_message(valid: bool) -> Value {
    let valid_path = Path::new("/Users/bwingfield/Downloads/msgs/valid_msg.json");
    let invalid_path = Path::new("/Users/bwingfield/Downloads/msgs/invalid_msg.json");
    let path = if valid {
        valid_path
    } else {
        invalid_path
    };

    let string_message = fs::read_to_string(&path).expect("File");
    let message: Value = serde_json::from_str(&string_message).expect("Valid JSON");
    return message;
}