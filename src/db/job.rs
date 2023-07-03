//! Job loading, updating, and submission to SLURM scheduler
//!
//! Takes care of deserialising unsubmitted jobs from the database into a JobRequest.
//! Also responsible for updating the database once JobRequests are staged (rendered templates written
//! to disk) or submitted (sbatch system command run).

pub mod load;
pub mod update;
pub mod state;