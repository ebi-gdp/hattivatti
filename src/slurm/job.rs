use std::{fs, io};
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

use chrono::Utc;
use log::info;
use serde::Serialize;
use serde_json::Value;
use tinytemplate::error::Error;
use tinytemplate::TinyTemplate;

use crate::slurm::job_request::{JobRequest, NxfParamsFile, PipelineParam, TargetGenome};
use crate::WorkingDirectory;

pub fn create_job(request: JobRequest, wd: &WorkingDirectory) {
    let instance_wd = WorkingDirectory { path: wd.path.join(&request.pipeline_param.id) };
    info!("Creating job {} in working directory {}", &request.pipeline_param.id, &instance_wd.path.display());
    fs::create_dir(&instance_wd.path).expect("Can't create working directory");
    let header: Header = render_header(&request.pipeline_param);
    let callback: Callback = render_callback(&request.pipeline_param);
    let vars: EnvVars = render_environment_variables(&request);
    let workflow: Workflow = render_nxf(&request.pipeline_param, &wd.path);
    let job = JobTemplate { header, callback, vars, workflow };
    job.write(&instance_wd.path.join("job.sh")).expect("Can't write job script");
    write_samplesheet(&request.pipeline_param, &instance_wd);
    write_config(&request.pipeline_param.nxf_params_file, &instance_wd);
    write_allas(&instance_wd);
}

struct JobTemplate {
    header: Header,
    callback: Callback,
    vars: EnvVars,
    workflow: Workflow,
}

impl JobTemplate {
    fn write(self, out_path: &Path) -> Result<(), io::Error> {
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(out_path)?;

        [self.header.content, self.callback.content, self.vars.content, self.workflow.content].map(
            |str| {
                file.write_all(str.as_bytes()).expect("Can't write job");
            }
        );

        Ok(())
    }
}

struct Callback {
    content: String,
}

struct Header {
    content: String,
}

struct EnvVars {
    content: String,
}

struct Workflow {
    content: String,
}

#[derive(Serialize)]
struct HeaderContext {
    name: String,
    job_time: String,
    time_now: String,
}

#[derive(Serialize)]
struct EnvVarContext {
    globus_base_url: String,
    guest_collection_id: String,
    message: String,
}

#[derive(Serialize)]
struct NextflowContext {
    name: String,
    work_dir: String,
    pgsc_calc_dir: String,
}

#[derive(Serialize)]
struct CallbackContext {
    name: String,
}

fn write_config(nxf_params: &NxfParamsFile, wd: &WorkingDirectory) {
    let params_file: String = serde_json::to_string(nxf_params).expect("Deserialised");
    let out_path = wd.path.join("params.json");
    info!("Writing params to {}", out_path.display());
    fs::write(out_path, params_file).expect("Can't write config");
}


fn write_samplesheet(param: &PipelineParam, wd: &WorkingDirectory) {
    let genomes: &Vec<TargetGenome> = &param.target_genomes;
    let samplesheet: String = serde_json::to_string(genomes).expect("Deserialised");
    let out_path = wd.path.join("input.json");
    info!("Writing samplesheet to {}", out_path.display());
    fs::write(out_path, samplesheet).expect("Can't write file");
}

fn write_allas(wd: &WorkingDirectory) {
    let allas: AllasConfig = allas_config();
    let out_path = wd.path.join("allas.config");
    info!("Writing allas config to {}", out_path.display());
    fs::write(out_path, allas.content).expect("Can't write file");
}

fn render_header(param: &PipelineParam) -> Header {
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

fn render_environment_variables(request: &JobRequest) -> EnvVars {
    static ENV_VARS: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/env_vars.txt"));
    let mut tt = TinyTemplate::new();
    // html escape breaks JSON
    tt.set_default_formatter(&tinytemplate::format_unescaped);
    tt.add_template("env_var", ENV_VARS).expect("Template");

    // todo: set globus base url dynamically
    let globus_base_url: String = "https://g-1504d5.dd271.03c0.data.globus.org".to_string();
    let guest_collection_id = request.globus_details.guest_collection_id.clone();
    let message: String = serde_json::to_string(&request).expect("Deserialised");
    let context = EnvVarContext { globus_base_url, guest_collection_id, message };

    EnvVars { content: tt.render("env_var", &context).expect("Rendered document") }
}

fn render_nxf(param: &PipelineParam, work_dir: &Path) -> Workflow {
    static NXF: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/nxf.txt"));
    let mut tt = TinyTemplate::new();
    tt.add_template("nxf", NXF).expect("Template");
    let name: &String = &param.id;
    let wd = work_dir.to_str().expect("path").to_string();
    // todo: make dynamic based on deployment namespace
    static PGSC_CALC_DIR: &str = "/scratch/project_2004504/pgsc_calc/";
    let context = NextflowContext { name: name.clone(), work_dir: wd, pgsc_calc_dir: PGSC_CALC_DIR.to_string() };
    Workflow { content: tt.render("nxf", &context).expect("Rendered nextflow") }
}

fn render_callback(param: &PipelineParam) -> Callback {
    static CALLBACK: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/callback.txt"));
    let mut tt = TinyTemplate::new();
    tt.add_template("callback", CALLBACK).expect("Template");
    let name: &String = &param.id;
    let context = CallbackContext { name: name.clone() };
    Callback { content: tt.render("callback", &context).expect("Rendered callback") }
}

struct AllasConfig {
    content: String,
}

fn allas_config() -> AllasConfig {
    static ALLAS: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/allas.config"));
    AllasConfig { content: ALLAS.to_string() }
}

