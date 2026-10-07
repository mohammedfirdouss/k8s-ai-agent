"""Score a diagnosis against a scenario's rubric."""

from dataclasses import asdict, dataclass

from evals.scenarios import Expectation, Groups, Scenario


@dataclass
class ExpectationScore:
    workload: str
    named_workload: bool
    cause: bool
    fix: bool
    # False when the incident claimed more confidence than the evidence allows.
    calibrated: bool = True

    @property
    def passed(self) -> bool:
        return self.named_workload and self.cause and self.fix and self.calibrated


@dataclass
class ScenarioScore:
    scenario: str
    error: "str | None"
    expectations: "list[ExpectationScore]"
    confidence: "float | None"
    # Control scenarios: incidents reported where none should be.
    false_alarms: int = 0

    @property
    def passed(self) -> bool:
        return self.error is None and self.false_alarms == 0 and all(e.passed for e in self.expectations)

    @property
    def coverage(self) -> float:
        """Fraction of the scenario's broken workloads diagnosed correctly."""
        if self.error is not None:
            return 0.0
        if not self.expectations:  # control scenario
            return 1.0 if self.false_alarms == 0 else 0.0
        return sum(e.passed for e in self.expectations) / len(self.expectations)

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "passed": self.passed,
            "coverage": self.coverage,
            "expectations": [{**asdict(e), "passed": e.passed} for e in self.expectations],
        }


def matches(text: str, groups: Groups) -> bool:
    """True when every group has at least one alternative present in text."""
    lowered = text.lower()
    return all(any(alt.lower() in lowered for alt in group) for group in groups)


def score(scenario: Scenario, diagnosis: dict) -> ScenarioScore:
    """Score each expected problem against the incident(s) about its workload.

    An expectation passes only when one incident both names the workload and
    gives the right cause and fix, so a correct cause attached to the wrong
    workload does not count.
    """
    incidents = diagnosis.get("incidents")
    if incidents is None:  # pre-incident flat diagnosis format
        incidents = [diagnosis]

    return ScenarioScore(
        scenario=scenario.id,
        error=diagnosis.get("error"),
        confidence=diagnosis.get("confidence"),
        expectations=[_score_expectation(e, incidents) for e in scenario.expectations],
        false_alarms=len(incidents) if scenario.expect_healthy and diagnosis.get("incidents") is not None else 0,
    )


def _texts(incident: dict) -> "tuple[str, str]":
    cause = " ".join(filter(None, [incident.get("root_cause"), incident.get("explanation")]))
    fix = " ".join(filter(None, [incident.get("fix"), *(incident.get("kubectl_commands") or [])]))
    return cause, fix


def _score_expectation(expectation: Expectation, incidents: "list[dict]") -> ExpectationScore:
    best = ExpectationScore(workload=expectation.workload, named_workload=False, cause=False, fix=False)
    for incident in incidents:
        cause_text, fix_text = _texts(incident)
        all_text = " ".join(filter(None, [incident.get("workload"), cause_text, fix_text]))
        if expectation.workload.lower() not in all_text.lower():
            continue
        confidence = incident.get("confidence")
        candidate = ExpectationScore(
            workload=expectation.workload,
            named_workload=True,
            cause=matches(cause_text, expectation.cause),
            fix=matches(fix_text, expectation.fix),
            calibrated=expectation.max_confidence is None
            or (confidence is not None and confidence <= expectation.max_confidence),
        )
        if candidate.passed or (candidate.cause + candidate.fix) > (best.cause + best.fix) or not best.named_workload:
            best = candidate
    return best
