use std::fs;
use std::path::{Path, PathBuf};

use jsonschema::JSONSchema;
use log::{info, warn};
use serde_json::Value;
use crate::request::read;
use anyhow::Result;
use crate::request::job::JobRequest;
use crate::request::message::MessageError::JSONValidationError;

#[derive(Debug)]
pub enum MessageError {
    JSONValidationError,
    JSONDecodeError,
    DeserialisationError,
    MessageReadError,
}

pub struct Message {
    pub path: PathBuf
}

pub fn from_dir(dir: &Path) -> Result<Vec<Message>> {
    let mut list: Vec<Message> = Vec::new();

    let paths= read::get_message_paths(dir)?;

    for path in paths {
        let m = Message { path };
        list.push(m);
    }

    Ok(list)
}

impl Message {
    pub fn read(&self, schema: &JSONSchema) -> Result<JobRequest, MessageError> {
        let json: Value = self.parse_untyped_json()?;

        match self.validate(&json, schema) {
            Ok(_) => {
                info!("Message is valid");
                self.parse_json(json)
            }
            Err(err) => {
                warn!("Message fails validation");
                warn!("{:?}", err);
                Err(err)
            }
        }
    }

    fn validate(&self, json_string: &Value, schema: &JSONSchema) -> Result<(), MessageError> {
        info!("Validating raw message against JSON validate");
        match schema.validate(json_string) {
            Ok(_) => Ok(()),
            Err(errors) => {
                for error in errors {
                    warn!("Validation error: {}", error);
                    warn!("Instance path: {}", error.instance_path);
                }
                Err(JSONValidationError)
            }
        }
    }

    fn read_file(&self) -> Result<String, MessageError> {
        let path: &Path = self.path.as_path();
        info!("Reading message at {}", path.display());
        fs::read_to_string(path).map_err(|err| {
            warn!("Can't read message job request at path {}: {}", path.display(), err);
            MessageError::MessageReadError
        })
    }

    fn parse_json(&self, value: Value) -> Result<JobRequest, MessageError> {
        info!("Deserialising valid JSON into typed Rust object");
        // from_value is a generic function, so request JobRequest specifically
        serde_json::from_value::<JobRequest>(value)
            .map_err(|_| MessageError::DeserialisationError)
    }

    fn parse_untyped_json(&self) -> Result<Value, MessageError> {
        info!("Parsing JSON into untyped structure");
        let json_string = self.read_file()?;
        info!("{}", json_string);
        // from_value is a generic function, so request Value (generic json) specifically
        serde_json::from_str::<Value>(&json_string)
            .map_err(|_| MessageError::JSONDecodeError)
    }
}
