# pyvatti

pyvatti is a FastAPI application for launching PGS Catalog Calculator jobs in different environments.

## Installation

```bash
$ git clone https://github.com/ebi-gdp/hattivatti.git
$ cd hattivatti/pyvatti
$ poetry install
```

## Usage

```bash
$ fastapi src/pyvatti/main.py
```

## Configuration

`pyvatti` requires some environment variables to be set. See [src/pyvatti/config.py](https://github.com/ebi-gdp/hattivatti/blob/main/pyvatti/src/pyvatti/config.py)

## Developer notes

* The most important class is [`PolygenicScoreJob`](https://github.com/ebi-gdp/hattivatti/blob/main/pyvatti/src/pyvatti/job.py), which inherits from an asynchronous state machine class [provided by transitions](https://github.com/pytransitions/transitions)
* Triggering changes to state causes [compute resources](https://github.com/ebi-gdp/hattivatti/blob/main/pyvatti/src/pyvatti/resources.py) to be created or destroyed, or notifications to be sent to the backend.
* Everything else is pretty standard for a FastAPI application
