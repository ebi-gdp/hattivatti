use std::fmt;
use clap::ValueEnum;

#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
pub enum PlatformNamespace {
    Dev,
    Test,
    Prod
}

impl fmt::Display for PlatformNamespace {
      fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            PlatformNamespace::Dev => write!(f, "dev"),
            PlatformNamespace::Test => write!(f, "test"),
            PlatformNamespace::Prod => write!(f, "prod")
        }
    }
}