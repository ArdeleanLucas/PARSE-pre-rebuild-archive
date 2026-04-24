import pathlib
import sys
from http import HTTPStatus

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, path: str = "/api/jobs"):
        self.path = path
        self.sent = []

    def _send_json(self, status, payload):
        self.sent.append((status, payload))


def test_job_logs_capture_lifecycle_and_progress() -> None:
    server._jobs.clear()

    job_id = server._create_job("normalize", {"speaker": "Fail01"})
    server._set_job_progress(job_id, 10.0, message="Scanning loudness (pass 1)")
    server._set_job_progress(job_id, 40.0, message="Normalizing audio (pass 2)")
    server._set_job_complete(job_id, {"speaker": "Fail01"}, message="Normalize complete")

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    logs = snapshot.get("logs")
    assert isinstance(logs, list)
    assert len(logs) >= 4
    assert logs[0]["event"] == "job.created"
    assert logs[1]["message"] == "Scanning loudness (pass 1)"
    assert logs[2]["message"] == "Normalizing audio (pass 2)"
    assert logs[-1]["event"] == "job.completed"
    assert logs[-1]["message"] == "Normalize complete"


def test_api_get_jobs_and_job_logs_return_generic_observability_payloads() -> None:
    server._jobs.clear()

    running_job = server._create_job("stt", {"speaker": "Fail01"})
    finished_job = server._create_job("normalize", {"speaker": "Fail02"})
    server._set_job_progress(running_job, 25.0, message="Transcribing")
    server._set_job_complete(finished_job, {"speaker": "Fail02"}, message="Normalize complete")

    handler = _HandlerHarness("/api/jobs")
    handler._api_get_jobs()
    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["count"] == 2
    by_id = {job["jobId"]: job for job in payload["jobs"]}
    assert by_id[running_job]["status"] == "running"
    assert by_id[finished_job]["status"] == "complete"
    assert by_id[running_job]["logCount"] >= 2

    handler._api_get_job(running_job)
    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == running_job
    assert payload["type"] == "stt"
    assert payload["meta"]["speaker"] == "Fail01"

    handler.path = "/api/jobs/{0}/logs".format(running_job)
    handler._api_get_job_logs(running_job)
    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == running_job
    assert payload["count"] >= 2
    assert payload["logs"][-1]["message"] == "Transcribing"
