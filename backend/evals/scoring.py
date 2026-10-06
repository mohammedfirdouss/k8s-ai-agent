"""Score a diagnosis against a scenario's rubric."""

from dataclasses import asdict, dataclass

from evals.scenarios import Expectation, Groups, Scenario


@dataclass
class ExpectationScore:
    workload: str
    named_workload: bool
    cause: bool
    fix: bool

    @property
    def passed(self) -> bool:
        return self.named_workload and self.cause and self.fix


@dataclass
class ScenarioScore:
    scenario: str
    error: "str | None"
    expectations: "list[ExpectationScore]"
    confidence: "float | None"

    @property
    def passed(self) -> bool:
        return self.error is None and all(e.passed for e in self.expectations)

    @property
    def coverage(self) -> float:
        """Fraction of the scenario's broken workloads diagnosed correctly."""
        if self.error is not None or not self.expectations:
            return 0.0
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
    cause_text = " ".join(filter(None, [diagnosis.get("root_cause"), diagnosis.get("explanation")]))
    fix_text = " ".join(
        filter(None, [diagnosis.get("fix"), *(diagnosis.get("kubectl_commands") or [])])
    )
    all_text = f"{cause_text} {fix_text}"

    return ScenarioScore(
        scenario=scenario.id,
        error=diagnosis.get("error"),
        confidence=diagnosis.get("confidence"),
        expectations=[_score_expectation(e, cause_text, fix_text, all_text) for e in scenario.expectations],
    )


def _score_expectation(
    expectation: Expectation, cause_text: str, fix_text: str, all_text: str
) -> ExpectationScore:
    return ExpectationScore(
        workload=expectation.workload,
        named_workload=expectation.workload.lower() in all_text.lower(),
        cause=matches(cause_text, expectation.cause),
        fix=matches(fix_text, expectation.fix),
    )
