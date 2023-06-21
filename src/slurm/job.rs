use std::fs::OpenOptions;
use std::io;
use std::io::Write;
use std::path::Path;

use log::info;
use serde::Serialize;
use serde_json::Value;
use tinytemplate::error::Error;
use tinytemplate::TinyTemplate;

use chrono::Utc;

use crate::slurm::job_request::{JobRequest, NxfParamsFile, PipelineParam};
use crate::WorkingDirectory;

pub fn create_job(request: JobRequest, wd: &WorkingDirectory) {
    info!("Creating job {}", &request.pipeline_param.id);
    let header: Header = render_header(&request.pipeline_param);
    let vars: EnvVars = render_environment_variables(&request);
    let workflow: Workflow = render_nxf(&request.pipeline_param, &wd.path);
    let job = JobTemplate { header, vars, workflow };
    job.write(Path::new("/Users/bwingfield/Downloads/test.txt")).expect("out");

    let _ = make_input_file(&request.pipeline_param.nxf_params_file);
}

struct JobTemplate {
    header: Header,
    vars: EnvVars,
    workflow: Workflow,
}

impl JobTemplate {
    fn write(self, out_path: &Path) -> Result<(), io::Error> {
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(out_path)?;

        [self.header.content, self.vars.content, self.workflow.content].map(
            |str| {
                file.write_all(str.as_bytes());
            }
        );

        Ok(())
    }
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
    time_now: String
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
}


fn render_header(param: &PipelineParam) -> Header {
    static HEADER: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/header.txt"));
    let mut tt = TinyTemplate::new();
    tt.add_template("header", HEADER).expect("Template");

    let context = HeaderContext {
        name: param.id.to_string(),
        // (todo: run job for 1 hour)
        job_time: "01:00:00".to_string(),
        time_now: Utc::now().to_string()
    };

    Header { content: tt.render("header", &context).expect("Rendered document") }
}

fn render_environment_variables(request: &JobRequest) -> EnvVars {
    static ENV_VARS: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/env_vars.txt"));
    let mut tt = TinyTemplate::new();
    // html escape breaks JSON
    tt.set_default_formatter(&tinytemplate::format_unescaped);
    tt.add_template("env_var", ENV_VARS).expect("Template");

    let globus_base_url: String = "https://g-1504d5.dd271.03c0.data.globus.org".to_string();
    let guest_collection_id = request.globus_details.guest_collection_id.clone();
    let message: String = serde_json::to_string(&request.pipeline_param).expect("Deserialised");
    let context = EnvVarContext { globus_base_url, guest_collection_id, message };

    EnvVars { content: tt.render("env_var", &context).expect("Rendered document") }
}


fn render_nxf(param: &PipelineParam, work_dir: &Path) -> Workflow {
    static NXF: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/nxf.txt"));
    let mut tt = TinyTemplate::new();
    tt.add_template("nxf", NXF).expect("Template");
    let name: &String = &param.id;
    let wd = work_dir.to_str().expect("path").to_string();
    let context = NextflowContext { name: name.clone(), work_dir: wd };
    Workflow { content: tt.render("nxf", &context).expect("Rendered document") }
}

struct AllasConfig {
    content: String,
}

fn allas_config() -> AllasConfig {
    static ALLAS: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/templates/allas.config"));
    AllasConfig { content: ALLAS.to_string() }
}

// pgsc_calc requires --input in json format (samplesheet)
// this describes the structure of the input genomes
fn make_input_file(params_file: &NxfParamsFile) {
    let val: Value = serde_json::to_value(params_file).expect("Deserialised params file");
    info!("{:?}", val);
}