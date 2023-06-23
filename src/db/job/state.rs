pub enum JobState {
    Staged,
    Submitted
}

impl JobState {
    /// db columns are all lower case, enum used in sql statement
    pub fn to_string(&self) -> &str {
        match self {
            JobState::Staged => "staged",
            JobState::Submitted => "submitted"
        }
    }
}