use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Serialize)]
pub struct PipelineParam {
    pub id: String,
    pub target_genomes: Vec<TargetGenome>,
    pub nxf_params_file: NxfParamsFile,
    pub nxf_work: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct TargetGenome {
    pvar: String,
    pgen: String,
    psam: String,
    sampleset: String,
    chrom: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct NxfParamsFile {
    pgs_id: String,
    format: String,
    target_build: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct GlobusDetails {
    pub guest_collection_id: String,
    pub dir_path_on_guest_collection: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct JobRequest {
    pub pipeline_param: PipelineParam,
    pub globus_details: GlobusDetails,
}
