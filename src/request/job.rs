use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Serialize)]
pub struct PipelineParam {
    pub id: String,
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
pub struct GlobusDetails {
    guest_collection_id: String,
    dir_path_on_guest_collection: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct JobRequest {
    pub pipeline_param: PipelineParam,
    globus_details: GlobusDetails,
}
