from app.kubernetes import kubectl
from app.kubernetes.kubectl import Kubectl


def test_each_instance_targets_its_own_context(monkeypatch):
    commands = []

    class Done:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(command, **_kwargs):
        commands.append(command)
        return Done()

    monkeypatch.setattr(kubectl.subprocess, "run", fake_run)
    prod, staging = Kubectl("prod"), Kubectl("staging")
    prod.run(["get", "pods"])
    staging.run(["get", "pods"])
    prod.run(["get", "svc"])

    assert commands[0][-2:] == ["--context", "prod"]
    assert commands[1][-2:] == ["--context", "staging"]
    assert commands[2][-2:] == ["--context", "prod"]


def test_config_commands_skip_context(monkeypatch):
    seen = []
    monkeypatch.setattr(
        kubectl.subprocess,
        "run",
        lambda command, **_: seen.append(command) or type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    Kubectl("prod").run(["config", "get-contexts"])
    assert "--context" not in seen[0]
