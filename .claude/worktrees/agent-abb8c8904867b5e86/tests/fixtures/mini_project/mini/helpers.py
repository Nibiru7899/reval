"""Shared arithmetic for the mini producers (a helper module, so code_hash covers more than one file)."""

from typing import Any

from reval.domain.engineering import Subject, SubjectKind


def peak_load(subject: Subject) -> float:
    """Maximum of the duty cycle's load profile."""
    load: Any = subject.params["load"]
    return float(max(load))


def is_duty_cycle(subject: Subject) -> bool:
    return subject.kind is SubjectKind.DUTY_CYCLE
