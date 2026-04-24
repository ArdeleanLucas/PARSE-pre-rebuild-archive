import pathlib
import sys
from http import HTTPStatus

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, path: str = "/api/jobs", body=None):
        self.path = path
        self._body = body or {}
        self.sent = []

    def _read_json_body(self, required: bool = True):
        return self._body

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


def test_job_lifecycle_supports_queued_running_and_error_states(monkeypatch) -> None:
    server._jobs.clear()
    monkeypatch.setenv("PARSE_JOB_LOG_MAX_ENTRIES", "20")

    job_id = server._create_job("compute:full_pipeline", {"speaker": "Fail03"}, initial_status="queued")
    server._set_job_running(job_id, message="Dequeued for execution")
    server._set_job_progress(job_id, 15.0, message="Running pipeline")
    server._set_job_error(job_id, "ffmpeg failed with exit code 1")

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["status"] == "error"
    assert snapshot["error_code"] == "ffmpeg_failed"
    events = [entry["event"] for entry in snapshot["logs"]]
    assert events[:2] == ["job.queued", "job.started"]
    assert events[-1] == "job.failed"


def test_job_log_ring_buffer_size_is_configurable(monkeypatch) -> None:
    server._jobs.clear()
    monkeypatch.setenv("PARSE_JOB_LOG_MAX_ENTRIES", "10")

    job_id = server._create_job("stt", {"speaker": "Fail04"})
    for idx in range(20):
        server._set_job_progress(job_id, float(idx), message="step-{0}".format(idx))

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert len(snapshot["logs"]) == 10
    assert snapshot["logs"][-1]["message"] == "step-19"


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


def test_backward_compatible_status_endpoints_still_return_job_payloads() -> None:
    server._jobs.clear()

    stt_job = server._create_job("stt", {"speaker": "Fail01"})
    normalize_job = server._create_job("normalize", {"speaker": "Fail02"})
    server._set_job_progress(stt_job, 35.0, message="Transcribing")
    server._set_job_error(normalize_job, "ffmpeg failed with exit code 1")

    stt_handler = _HandlerHarness("/api/stt/status", {"jobId": stt_job})
    stt_handler._api_post_stt_status()
    status, payload = stt_handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == stt_job
    assert payload["status"] == "running"

    normalize_handler = _HandlerHarness("/api/normalize/status", {"jobId": normalize_job})
    normalize_handler._api_post_normalize_status()
    status, payload = normalize_handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == normalize_job
    assert payload["status"] == "error"
    assert payload["errorCode"] == "ffmpeg_failed"
