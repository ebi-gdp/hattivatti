use std::{fs, io};
use std::io::Error;
use std::path::{Path, PathBuf};

pub fn get_message_paths(dir: &Path) -> Result<Vec<PathBuf>, Error> {
    fs::read_dir(dir)?
        .map(|res| res.map(|e| e.path()))
        .collect::<Result<Vec<PathBuf>, io::Error>>()
}