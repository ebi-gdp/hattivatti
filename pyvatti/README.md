# pyvatti

pyvatti is a python service for launching PGS Catalog Calculator jobs for GeneticScores.org jobs in different environments.

## Developer instructions 

Set up a virtual environment using nox and uv:

```bash
$ git clone https://github.com/ebi-gdp/hattivatti.git
$ cd hattivatti/pyvatti
$ nox -s dev
```

## Usage

```bash
$ source .venv/bin/activate
$ pyvatti 
```

## Configuration

`pyvatti` requires some environment variables to be set. See [src/pyvatti/config.py](https://github.com/ebi-gdp/hattivatti/blob/main/pyvatti/src/pyvatti/config.py)

## Developer notes

* The most important class is [`PolygenicScoreJob`](https://github.com/ebi-gdp/hattivatti/blob/main/pyvatti/src/pyvatti/pgsjob.py), which inherits from a state machine class [provided by transitions](https://github.com/pytransitions/transitions)
* Triggering changes to state causes [compute resources](https://github.com/ebi-gdp/hattivatti/blob/main/pyvatti/src/pyvatti/resources.py) to be created or destroyed, or notifications to be sent to the backend
* [`helmvatti`](https://github.com/ebi-gdp/hattivatti/tree/main/pyvatti/helmvatti/) is a Helm chart for installing the PGS Catalog Calculator to a kubernetes cluster, deploying compute workers externally (i.e. to Google Batch)
* A temporary sqlite database is used to store and update jobs by default. For production environments this can be backed up using [litestream](https://litestream.io/) (implemented in the hattivatti application [helm chart](https://github.com/ebi-gdp/hattivatti/tree/main/chart)).
