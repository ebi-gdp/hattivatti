use std::{error, fs, io, panic};
use std::path::{Path, PathBuf};

use jsonschema::{ErrorIterator, JSONSchema, ValidationError};
use log::{info, warn};
use serde::{Deserialize, Serialize};
use serde_json::{Error, Value};

enum MessageError {
    ValidationFailed,
    SerializationError,
    ParseError,
}

pub struct Message {
    pub path: PathBuf,
    pub compiled_schema: JSONSchema,
}

impl Message {
    pub fn read(&self) -> Option<JobRequest> {
        let valid: bool = self.validate().is_ok();
        if valid {
            info!("Message is valid");
        } else {
            warning!("Message is invalid");
        }
        // if validation fails, parsing into strong types will also fail
        // todo: change from option to Result 
        return self.parse_json();
    }

    fn validate(&self) -> Result<(), MessageError> {
        info!("Validating raw message against JSON schema");
        let job = self.parse_untyped_json().ok_or(MessageError::ParseError)?;
        let value = serde_json::to_value(&job).map_err(|_| MessageError::SerializationError)?;
        self.compiled_schema.validate(&value).map_err(|_| MessageError::ValidationFailed)?;
        Ok(())
    }


    fn read_file(&self) -> Result<String, io::Error> {
        let path = self.path.as_path();
        info!("Reading file at {}", path.display());
        fs::read_to_string(path).map_err(|err| {
            warn!("Can't read message job request at path {}: {}", path.display(), err);
            err
        })
    }

    fn parse_json(&self) -> Option<JobRequest> {
        info!("Deserialising JSON into typed Rust object");
        self.read_file()
            .ok()
            .and_then(|string_json| {
                serde_json::from_str(&string_json).map_err(|err| {
                    warn!("Error parsing JSON: {}", err);
                }).ok()
            })
    }

    fn parse_untyped_json(&self) -> Option<Value> {
        info!("Parsing JSON into untyped structure");
        self.read_file()
            .ok()
            .and_then(|string_json| {
                serde_json::from_str(&string_json).map_err(|err| {
                    warn!("Error parsing JSON: {}", err);
                }).ok()
            })
    }
}


#[derive(Debug, Deserialize, Serialize)]
struct PipelineParam {
    id: String,
    target_genomes: Vec<TargetGenome>,
    nxf_params_file: NxfParamsFile,
    nxf_work: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct TargetGenome {
    pvar: String,
    pgen: String,
    psam: String,
    sampleset: String,
    chrom: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
struct NxfParamsFile {
    pgs_id: String,
    format: String,
    target_build: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct GlobusDetails {
    guest_collection_id: String,
    dir_path_on_guest_collection: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct JobRequest {
    pipeline_param: PipelineParam,
    globus_details: GlobusDetails,
}
