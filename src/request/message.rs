use std::{fs, io};
use std::io::ErrorKind;
use std::path::{Path, PathBuf};

use jsonschema::JSONSchema;
use log::{info, warn};
use serde_json::Value;

pub struct Message {
    pub path: PathBuf,
}

pub fn from_dir(dir: &Path) -> Result<Vec<Message>, io::Error> {
    let mut list: Vec<Message> = Vec::new();

    let paths = get_message_paths(dir)?;

    for path in paths {
        let m = Message { path };
        list.push(m);
    }

    Ok(list)
}

impl Message {
    pub fn read(&self, schema: &JSONSchema) -> Result<(), io::Error> {
        let json: Value = self.parse_untyped_json()?;

        match self.validate(&json, schema) {
            Ok(_) => {
                info!("Message is valid");
                Ok(())
            }
            Err(err) => {
                warn!("Message fails validation");
                warn!("{:?}", err);
                Err(err)
            }
        }
    }

    fn validate(&self, json_string: &Value, schema: &JSONSchema) -> Result<(), io::Error> {
        info!("Validating raw message against JSON validate");
        match schema.validate(json_string) {
            Ok(_) => Ok(()),
            Err(errors) => {
                for error in errors {
                    warn!("Validation error: {}", error);
                    warn!("Instance path: {}", error.instance_path);
                }
                let err = io::Error::new(ErrorKind::Other, "JSON validation error");
                Err(err)
            }
        }
    }

    fn read_file(&self) -> Result<String, io::Error> {
        let path: &Path = self.path.as_path();
        info!("Reading message at {}", path.display());
        let contents = fs::read_to_string(path)?;
        Ok(contents)
    }

    fn parse_untyped_json(&self) -> Result<Value, io::Error> {
        let json_string = self.read_file()?;
        info!("Parsing JSON into untyped structure: {}", json_string);
        let value: Value = serde_json::from_str(&json_string)?;
        Ok(value)
    }
}

fn get_message_paths(dir: &Path) -> Result<Vec<PathBuf>, io::Error> {
    fs::read_dir(dir)?
        .map(|res| res.map(|e| e.path()))
        .collect::<Result<Vec<PathBuf>, io::Error>>()
}
