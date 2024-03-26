from fastapi import FastAPI

from .models import PGSJob

app = FastAPI()


@app.post("/launch")
async def launch(job: PGSJob):
    return job
