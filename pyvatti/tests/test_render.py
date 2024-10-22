import json

import pytest

from pyvatti.helm import render_template
from pyvatti.messagemodels import JobRequest


@pytest.fixture()
def message(request):
    return request.path.parent / "data" / "test.json"


def test_render(message):
    """Test a values.yaml helm file is templated and rendered correctly"""
    with open(message) as f:
        msg = json.loads(f.read())
    job: JobRequest = JobRequest(**msg)
    template: dict = render_template(
        job=job, work_bucket_path="testpathwork/", results_bucket_path="testpathresults"
    )

    # some basic checks:
    # check secrets have been templated using environments variables (from settings object)
    assert template["secrets"]["globusClientSecret"] == "test"
    assert template["secrets"]["globusDomain"] == "https://example.com"

    # check parameters have been set in the template
    assert template["nxfParams"]["gcpProject"] == "testproject"
