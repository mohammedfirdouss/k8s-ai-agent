from datetime import datetime, timedelta, timezone

from app.kubernetes.inspectors import _pod_problem_state

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def running_pod(restarts, last_reason, started_ago):
    return {
        "status": {
            "phase": "Running",
            "containerStatuses": [{
                "ready": True,
                "restartCount": restarts,
                "state": {"running": {"startedAt": iso(NOW - started_ago)}},
                "lastState": {"terminated": {"reason": last_reason, "finishedAt": iso(NOW - started_ago)}},
            }],
        }
    }


def test_recently_restarted_container_is_flagged():
    assert _pod_problem_state(running_pod(2, "Completed", timedelta(seconds=10)), NOW) == "RestartingRecently"


def test_container_stable_since_last_restart_is_healthy():
    assert _pod_problem_state(running_pod(2, "Error", timedelta(minutes=20)), NOW) is None


def test_node_reboot_restart_is_not_an_app_problem():
    assert _pod_problem_state(running_pod(1, "Unknown", timedelta(seconds=30)), NOW) is None


def test_running_but_not_ready_is_flagged():
    pod = {"status": {"phase": "Running", "containerStatuses": [{"ready": False, "restartCount": 0, "state": {"running": {}}}]}}
    assert _pod_problem_state(pod, NOW) == "NotReady"


def test_stuck_init_container_is_flagged():
    pod = {"status": {"phase": "Pending", "initContainerStatuses": [
        {"state": {"waiting": {"reason": "CrashLoopBackOff"}}}], "containerStatuses": []}}
    assert _pod_problem_state(pod, NOW) == "Init:CrashLoopBackOff"


def test_completed_job_pod_is_healthy():
    assert _pod_problem_state({"status": {"phase": "Succeeded"}}, NOW) is None
