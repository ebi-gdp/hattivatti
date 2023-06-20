use std::fs;
use std::path::{Path, PathBuf};
use jsonschema::JSONSchema;
use log::{info, warn};
use serde_json::Value;
use serde::{Deserialize, Serialize};


#[derive(Debug)]
pub enum MessageError {
    JSONValidationError,
    JSONDecodeError,
    DeserialisationError,
    MessageReadError,
}

pub struct Message {
    pub path: PathBuf,
    pub compiled_schema: JSONSchema,
}

impl Message {
    pub fn read(&self) -> Result<JobRequest, MessageError> {
        let json: Value = self.parse_untyped_json()?;

        match self.validate(&json) {
            Ok(_) => {
                info!("Message is valid");
                self.parse_json(json)
            }
            Err(err) => {
                warn!("Message fails validation");
                Err(err)
            }
        }
    }

    fn validate(&self, json_string: &Value) -> Result<(), MessageError> {
        info!("Validating raw message against JSON schema");
        match self.compiled_schema.validate(json_string) {
            Ok(_) => Ok(()),
            Err(_) => Err(MessageError::JSONValidationError),
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
        // from_value is a generic function, so request Value (generic json) specifically
        serde_json::from_str::<Value>(&json_string)
            .map_err(|_| MessageError::JSONDecodeError)
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
