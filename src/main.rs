use std::fs;
use std::path::Path;
use log::{info,warn};


fn main() {
    env_logger::init();
    info!("terve! starting up :)");

    let path = Path::new("/Users/bwingfield/Downloads/msgs/msg.jsn");
    let x = read_job_request(&path);
    println!("{}", x.unwrap_or_default());

}

fn read_job_request(file_path: &Path) -> Option<String> {
    return match fs::read_to_string(file_path) {
        Ok(string) => {
            info!("Reading job request: {}", file_path.display());
            Some(string)
        }
        Err(_) => {
            warn!("Can't read job request at path: {}", file_path.display());
            None
        }
    }
}
