pub enum JobState {
    Staged,
    Submitted
}

/// A simple way to keep track of job state.
///
/// Currently only two states are supported: staged (rendered templates written to disk) and
/// submitted (after sbatch system command exits 0). Other job states could include things like
/// INITIALISED (request received) or PENDING (parsing squeue output) in the future.
impl JobState {
    /// db columns are all lower case, enum used in sql statement
    /// TODO: migrate to a single enum column called "state"
    pub fn to_string(&self) -> &str {
        match self {
            JobState::Staged => "staged",
            JobState::Submitted => "submitted"
        }
    }
}