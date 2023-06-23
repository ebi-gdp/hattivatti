use std::io;
use std::io::ErrorKind;

use jsonschema::JSONSchema;
use log::{info, warn};
use rusoto_s3::S3;
use serde_json::Value;
use tokio::io::AsyncReadExt;

pub fn make_allas_client() -> rusoto_s3::S3Client {
    let region = rusoto_core::Region::Custom {
        name: "us-east-1".to_owned(),
        endpoint: "https://a3s.fi".to_owned(), // Replace with the endpoint URL of your S3-compatible object store
    };

    let access_key = std::env::var("AWS_ACCESS_KEY_ID")
        .expect("AWS_ACCESS_KEY_ID environment variable not set");
    let secret_key = std::env::var("AWS_SECRET_ACCESS_KEY")
        .expect("AWS_SECRET_ACCESS_KEY environment variable not set");

    let credentials_provider = rusoto_credential::StaticProvider::new_minimal(access_key, secret_key);

    rusoto_s3::S3Client::new_with(rusoto_core::HttpClient::new().unwrap(),
                                  credentials_provider,
                                  region)
}

pub struct AllasMessage {
    pub bucket: String,
    pub key: String,
    pub content: String,
    pub valid: bool
}

pub async fn fetch_all(s3_client: &rusoto_s3::S3Client, schema: &JSONSchema) -> Option<Vec<AllasMessage>> {
    let bucket = "intervene-dev";
    let prefix = "job-queue";

    let list_request = rusoto_s3::ListObjectsV2Request {
        bucket: bucket.into(),
        prefix: Some(prefix.into()),
        ..Default::default()
    };

    let objects = s3_client.list_objects_v2(list_request)
        .await
        .expect("List of objects in bucket")
        .contents;

    let mut jobs: Vec<AllasMessage> = Vec::new();

    match objects {
        None => { return None; }
        Some(objects) => {
            for object in objects {
                let key = object.key.unwrap();
                info!("Object key: {}", key);
                let content = read_job(&s3_client, bucket, &key).await;
                info!("Object content: {content}");
                jobs.push(AllasMessage::new(content,
                                            bucket.to_string(),
                                            key,
                                            &schema));
            }
        }
    }

    Some(jobs)
}

async fn read_job(s3_client: &rusoto_s3::S3Client, bucket: &str, key: &String) -> String {
    let get_object_request = rusoto_s3::GetObjectRequest {
        bucket: bucket.into(),
        key: key.into(),
        ..Default::default()
    };

    let object = s3_client.get_object(get_object_request)
        .await
        .expect("Can't get object");

    let mut body = Vec::new();
    if let Some(stream) = object.body {
        stream
            .into_async_read()
            .read_to_end(&mut body)
            .await
            .expect("Failed to read file");
    }

    String::from_utf8_lossy(&body).to_string()
}


fn validate_message(json_string: &Value, schema: &JSONSchema) -> Result<(), io::Error> {
    info!("Validating message against JSON schema");
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

impl AllasMessage {
    pub fn new(content: String, bucket: String, key: String, schema: &JSONSchema) -> AllasMessage {
        info!("Parsing JSON into untyped structure");
        let value: Value = serde_json::from_str(&content).expect("Valid JSON");
        let valid: bool = validate_message(&value, &schema).is_ok();
        AllasMessage { content, bucket, key, valid }
    }

    pub async fn delete(&self, s3_client: &rusoto_s3::S3Client) {
        let bucket = self.bucket.to_string();
        let key = self.key.to_string();

        let delete_request = rusoto_s3::DeleteObjectRequest {
            bucket,
            key,
            ..Default::default()
        };

        match s3_client.delete_object(delete_request).await {
            Ok(_) => info!("{} deleted successfully.", &self.key),
            Err(err) => warn!("Error deleting {}: {}", &self.key, err),
        }
    }
}
