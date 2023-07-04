use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::anyhow;
use jsonschema::{JSONSchema, SchemaResolver, SchemaResolverError};
use log::{info};
use serde_json::{Value};
use url::Url;

/// Read, resolve, and compile the INTERVENE API JSON schema
pub fn load_schema(schema_dir: &Path) -> JSONSchema {
    info!("Reading schema from {}", schema_dir.display());
    let schema_json = read_schema(schema_dir);
    compile_schema(&schema_json, schema_dir)
}

/// Read the main INTERVENE API schema document
fn read_schema(schema_dir: &Path) -> Value {
    let schema_path = schema_dir.join("api.json");
    read_json_from_path(schema_path.as_path())
}

/// Read and load valid generic JSON
fn read_json_from_path(path: &Path) -> Value {
    let json_string = fs::read_to_string(path).expect("Valid path");
    serde_json::from_str(&json_string).expect("Valid JSON")
}

/// Resolve and compile a set of JSON schema for fast validation
fn compile_schema(schema: &Value, schema_dir: &Path) -> JSONSchema {
    let resolver = LocalResolver { schema_dir: PathBuf::from(schema_dir) };
    info!("Compiling JSON schema");
    JSONSchema::options()
        .with_resolver(resolver)
        .compile(schema)
        .expect("Valid schema")
}

/// A [SchemaResolver] that supports local JSON references
///
/// The local validate contain relative references to local files in the same directory
/// In the future we should change to online schemas with absolute references
struct LocalResolver {
    schema_dir: PathBuf,
}

impl SchemaResolver for LocalResolver {
    /// Resolve linked schema, assume linked schema are present in the same directory as the parent
    /// schema
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

