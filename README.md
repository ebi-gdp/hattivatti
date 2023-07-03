# `hattivatti`

`hattivatti` submits [`pgsc_calc`](https://github.com/PGScatalog/pgsc_calc) jobs
to [Puhti HPC](https://docs.csc.fi/computing/systems-puhti/) at CSC. Jobs are
configured to execute in a secure way because genomes are sensitive
data. `hattivatti` is a proof of concept for testing sensitive data submission
to CSC.

## Run `hattivatti`

See [Releases](https://github.com/ebi-gdp/hattivatti/releases) for most recent
stable versions of `hattivatti`. The development version can be run with:

```
$ git clone https://github.com/ebi-gdp/hattivatti.git --branch dev
$ cargo run
```

## Documentation

```
$ cargo doc --open
```

## Deployment notes

Puhti is currently on RHEL 7 with an old version of glibc.

Github actions builds with rust-buster to match glibc version (2.28).

### Cronjob

cron shell doesn't load much:

```
$ # load 'module' command
$ source /appl/profile/zz-csc-env.sh
```

### Set environment variables

Sensitive variables:

```
$ export GLOBUS_SECRET_TOKEN=<...>
$ export AWS_ACCESS_KEY_ID=<...>
$ export AWS_SECRET_ACCESS_KEY=<...>
$ export NXF_SINGULARITY_CACHEDIR=<...>
```

Configuration variables:

```
$ export RUST_LOG=info
$ export NXF_SINGULARITY_CACHEDIR=<path>
```

### Clone pgsc_calc

```
$ cd /scratch/projec_XXXXXX/
$ nextflow clone https://github.com/PGScatalog/pgsc_calc.git
```

### Run hattivatti

```
$ hattivatti --schema-dir repo/data/schemas  --work-dir work
```

### Backup database (optional)

After hattivatti executes the database will have no connections.

```
$ module load allas
$ rclone copy work/hattivatti.db s3allas://bucket/hattivatti/hattivatti.db
```

### Software dependencies

* `curl`
* `jq`
* `nextflow`
  * `java 16`
* `SLURM`