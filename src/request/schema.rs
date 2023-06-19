use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::anyhow;
use jsonschema::{JSONSchema, SchemaResolver, SchemaResolverError};
use log::warn;
use serde_json::{json, Value};
use url::Url;

pub fn load_schema(schema_dir: &Path) -> JSONSchema {
    let schema_json = read_schema(schema_dir);
    compile_schema(&schema_json, schema_dir)
}

fn read_schema(schema_dir: &Path) -> Value {
    let schema_path = schema_dir.join("api.json");
    read_json_from_path(schema_path.as_path())
}

fn read_json_from_path(path: &Path) -> Value {
    let json_string = fs::read_to_string(path).expect("Valid path");
    serde_json::from_str(&json_string).expect("Valid JSON")
}

fn compile_schema(schema: &Value, schema_dir: &Path) -> JSONSchema {
    let resolver = LocalResolver { schema_dir: PathBuf::from(schema_dir) };
    JSONSchema::options()
        .with_resolver(resolver)
        .compile(schema)
        .expect("Valid schema")
}

/*
Set up a resolver that will work with local JSON schema
The local schema contain relative references to local files in the same directory
In the future we should change to online schemas with absolute references
*/
struct LocalResolver {
    schema_dir: PathBuf,
}

impl SchemaResolver for LocalResolver {
    fn resolve(&self, _root_schema: &Value, url: &Url, _original_reference: &str) -> Result<Arc<Value>, SchemaResolverError> {
        match url.scheme() {
            "json-schema" => {
                let local_schema_path: PathBuf = self.schema_dir.join(_original_reference);
                Ok(Arc::new(read_json_from_path(local_schema_path.as_path())))
            }
            _ => Err(anyhow!("scheme is not supported"))
        }
    }
}

