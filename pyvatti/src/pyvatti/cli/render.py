import argparse
import json
import logging

import yaml

from pyvatti.config import Settings
from pyvatti.helm import render_template
from pyvatti.messagemodels import JobRequest

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="intervene-render-helm",
        description="This program renders a helm template values.yaml file based on a job request message",
        epilog="This is only really useful for debugging. You also need a .env file containing secrets to run this program.",
    )
    parser.add_argument("--message_path", required=True)
    parser.add_argument("--env_path", required=True)
    parser.add_argument("--bucket_name", required=True)

    parser.add_argument("--out_path", required=True)

    args = parser.parse_args()

    with open(args.message_path, mode="rt") as f:
        logger.info(f"Reading message from {args.message_path}")
        msg = json.loads(f.read())

    settings = Settings(_env_file=args.env_path)  # type: ignore

    job: JobRequest = JobRequest(**msg)
    template: dict = render_template(
        job=job,
        work_bucket_path=args.bucket_name,
        results_bucket_path=args.bucket_name,
        settings=settings,
    )
    logger.info("Rendered helm values file OK")

    with open(args.out_path, mode="wt") as f:
        yaml.dump(template, f)

    logger.info("Finished :)")


if __name__ == "__main__":
    main()
