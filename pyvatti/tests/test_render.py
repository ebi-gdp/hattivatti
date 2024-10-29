import json

import pytest

from pyvatti.helm import render_template
from pyvatti.messagemodels import JobRequest
from pyvatti.config import Settings


@pytest.fixture()
def message(request):
    return request.path.parent / "data" / "test.json"


def test_render(message):
    """Test a values.yaml helm file is templated and rendered correctly"""
    settings = Settings(
        TOWER_TOKEN="test",
        TOWER_WORKSPACE="test",
        GLOBUS_DOMAIN="https://example.com",
        GLOBUS_CLIENT_ID="test",
        GLOBUS_CLIENT_SECRET="test",
        GLOBUS_SCOPES="test",
        KAFKA_BOOTSTRAP_SERVER="kafka://localhost:9092",
        GCP_PROJECT="testproject",
        GCP_LOCATION="europe-west2",
    )

    with open(message) as f:
        msg = json.loads(f.read())
    job: JobRequest = JobRequest(**msg)
    template: dict = render_template(
        job=job,
        work_bucket_path="testpathwork/",
        results_bucket_path="testpathresults",
        settings=settings,
    )

    # some basic checks:
    # check secrets have been templated using environments variables (from settings object)
    assert template["secrets"]["globusClientSecret"] == "test"
    assert template["secrets"]["globusDomain"] == "https://example.com"

    # check parameters have been set in the template
    assert template["nxfParams"]["gcpProject"] == "testproject"
