use std::{fs, io};
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use chrono::Utc;
use log::{info, warn};
use serde::Serialize;
use tinytemplate::TinyTemplate;

use crate::slurm::job_request::{GlobusDetails, JobRequest, NxfParamsFile, PipelineParam, TargetGenome};
use crate::WorkingDirectory;

/// A JobPath is the path to a job script that's submitted to SLURM via sbatch
///
/// A JobPath **requires** the following files in the same directory:
/// - AllasConfig -> allas.config
/// - target_genomes -> input.json
/// - NxfParamsFile -> params.json
// TODO: add these paths to the struct to make this clearer
pub struct JobPath {
    pub path: PathBuf,
}

impl JobRequest {
    pub fn create(&self, wd: &WorkingDirectory, globus_path: &PathBuf) -> JobPath {
        let instance_wd = WorkingDirectory { path: wd.path.join(&&self.pipeline_param.id) };
        info!("Creating job {} in working directory {}", &&self.pipeline_param.id, &instance_wd.path.display());

        if instance_wd.path.exists() {
            warn!("Job directory already exists, files will be overwritten");
            fs::remove_dir_all(&instance_wd.path).expect("Delete existing directory");
        }
        fs::create_dir(&instance_wd.path).expect("Create working directory");

        let header: Header = render_header(&&self.pipeline_param);
        let callback: Callback = render_callback(&&self.pipeline_param);
        let vars: EnvVars = read_environment_variables();
        let workflow: Workflow = render_nxf(&globus_path, &&self.pipeline_param,  &wd.path);
        let job = JobTemplate { header, callback, vars, workflow };

        let path = &instance_wd.path.join("job.sh");
        job.write(path).expect("Can't write job script");
        write_samplesheet(&&self.pipeline_param, &instance_wd);
        write_config(&&self.pipeline_param.nxf_params_file, &instance_wd);
        write_allas(&instance_wd);
        write_transfer(&self.globus_details, &instance_wd);

        JobPath { path: path.clone() }
    }
}

/// All rendered data necessary to submit an INTERVENE pgsc_calc job to SLURM
struct JobTemplate {
    header: Header,
    callback: Callback,
    vars: EnvVars,
    workflow: Workflow,
}

impl JobTemplate {
    /// Write complete job script to disk by appending rendered template sections to the file
    fn write(self, out_path: &Path) -> Result<(), io::Error> {
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(out_path)?;

        // order is important when writing the file
        let contents = [
            self.header.content,
            self.callback.content,
            self.vars.content,
            self.workflow.content,
        ];

        for content in contents.iter() {
            file.write_all(content.as_bytes())?;
        }

        Ok(())
    }
}

/// Rendered HTTP callback
///
/// Uses curl to do a HTTP POST to the INTERVENE backend with job status. Currently supports two
/// states depending on exit status: 0 (succeeded) or not 0 (failed). Uses a bash trap to callback
/// when an error happens.
struct Callback {
    content: String,
}

/// Rendered SBATCH header
///
/// SLURM jobs options can be parsed by sbatch using #SBATCH headers [before executable commands](https://slurm.schedmd.com/sbatch.html#SECTION_DESCRIPTION).
/// Parts of the header should be set from message parameters, metadata, or CLI options, but only
/// some are only implemented:
/// - [X] job name
/// - [ ] queue / partition (small)
/// - [X] job time
/// - [ ] local node storage (256gb)
/// - [ ] job RAM
/// - [ ] account for billing usage
///
/// Other options shouldn't be changed:
/// - exclusive node execution
/// - exporting all environment variables
struct Header {
    content: String,
}

/// Rendered environment variables section
///
/// Environment variables are used to control nextflow execution and the globus transfer.
struct EnvVars {
    content: String,
}

/// Rendered workflow commands
///
/// Workflow commands include:
/// - loading dependencies using environment modules
/// - staging sensitive data to local node storage with a HTTP globus transfer
/// - running pgsc_calc with job-specific configuration
struct Workflow {
    content: String,
}

/// Rendering context for header
#[derive(Serialize)]
struct HeaderContext {
    name: String,
    job_time: String,
    time_now: String,
}

/// Rendering context for environment variables
#[derive(Serialize)]
struct EnvVarContext {
    globus_base_url: String,
    guest_collection_id: String,
    message: String,
}

/// Rendering context for workflow
#[derive(Serialize)]
struct NextflowContext {
    name: String,
    work_dir: String,
    pgsc_calc_dir: String,
    globus_path: String,
    globus_parent_path: String
}

/// Rendering context for callback
#[derive(Serialize)]
struct CallbackContext {
    name: String,
}

/// Write nextflow parameters to working directory
fn write_config(nxf_params: &NxfParamsFile, wd: &WorkingDirectory) {
    let params_file: String = serde_json::to_string(nxf_params).expect("Deserialised");
    let out_path = wd.path.join("params.json");
    info!("Writing params to {}", out_path.display());
    fs::write(out_path, params_file).expect("Can't write config");
}


/// Extract the target_genomes object to a JSON file (`pgsc_calc --input` parameter)
fn write_samplesheet(param: &PipelineParam, wd: &WorkingDirectory) {
    let genomes: &Vec<TargetGenome> = &param.target_genomes;
    let samplesheet: String = serde_json::to_string(genomes).expect("Deserialised");
    let out_path = wd.path.join("input.json");
    info!("Writing samplesheet to {}", out_path.display());
    fs::write(out_path, samplesheet).expect("Can't write file");
}

/// Write static Allas configuration to the working directory
fn write_allas(wd: &WorkingDirectory) {
    let allas: AllasConfig = allas_config();
    let out_path = wd.path.join("allas.config");
    info!("Writing allas config to {}", out_path.display());
    fs::write(out_path, allas.content).expect("Can't write file");
}

/// Render the SBATCH header using TinyTemplate
fn render_header(param: &PipelineParam) -> Header {
    /// included header template
    static HEADER: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/header.txt"));
    let mut tt = TinyTemplate::new();
    tt.add_template("header", HEADER).expect("Template");

    let context = HeaderContext {
        name: param.id.to_string(),
        // (todo: run job for 1 hour)
        job_time: "01:00:00".to_string(),
        time_now: Utc::now().to_string(),
    };

    Header { content: tt.render("header", &context).expect("Rendered document") }
}

/// Read environment variables from template
fn read_environment_variables() -> EnvVars {
    /// included environment variables template, everything is static
    static ENV_VARS: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/env_vars.txt"));
    EnvVars { content: ENV_VARS.to_string() }
}

/// Render the workflow commands using TinyTemplate
fn render_nxf(globus_path: &PathBuf, param: &PipelineParam, work_dir: &Path) -> Workflow {
    /// included workflow template
    static NXF: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/nxf.txt"));
    let mut tt = TinyTemplate::new();
    tt.add_template("nxf", NXF).expect("Template");
    let name: &String = &param.id;
    let wd = work_dir.to_str().expect("path").to_string();
    // todo: make dynamic based on deployment namespace
    /// installation directory of pgsc_calc (TODO: make this a parameter)
    static PGSC_CALC_DIR: &str = "/scratch/project_2004504/pgsc_calc/";
    let context = NextflowContext { name: name.clone(),
        work_dir: wd,
        pgsc_calc_dir: PGSC_CALC_DIR.to_string(),
        globus_path: globus_path.to_str().expect("Globus path").to_string(),
        globus_parent_path: globus_path.parent().expect("Globus parent").to_str().expect("Globus parent path").to_string()
    };
    Workflow { content: tt.render("nxf", &context).expect("Rendered nextflow") }
}

/// Render the callback using TinyTemplate
fn render_callback(param: &PipelineParam) -> Callback {
    /// included callback template
    static CALLBACK: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/callback.txt"));
    let mut tt = TinyTemplate::new();
    tt.add_template("callback", CALLBACK).expect("Template");
    let name: &String = &param.id;
    let context = CallbackContext { name: name.clone() };
    Callback { content: tt.render("callback", &context).expect("Rendered callback") }
}

/// Static nextflow configuration for publishing results to Allas
struct AllasConfig {
    content: String,
}

/// Load static allas configuration
fn allas_config() -> AllasConfig {
    /// included allas configuration (static)
    static ALLAS: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/allas.config"));
    AllasConfig { content: ALLAS.to_string() }
}

/// Write transfer details to a text file in the working directory
///
/// The text file is space delimited with two columns:
///
/// | dir path/filename                    | file_size |
/// | ------------------------------------ | --------- |
/// | bwingfield@ebi.ac.uk/ID/hapnest.psam | 8517      |
///
/// (no header is present in the output file)
fn write_transfer(globus: &GlobusDetails, wd: &WorkingDirectory) {
    let out_path = wd.path.join("transfer.txt");
    info!("Writing transfer requests to {}", out_path.display());

    let mut file = File::create(out_path).expect("Transfer file");
    for data in &globus.files {
        let line = format!("{}/{} {}\n", globus.dir_path_on_guest_collection, data.filename, data.file_size);
        file.write_all(&line.as_bytes()).expect("Line written");
    }
}