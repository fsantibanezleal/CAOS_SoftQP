"""Canonical scientific case registry; no hidden or learned model slot."""

from .softqp_cases import cases


def list_cases():
    return cases()


def get_case(case_id):
    try:
        return next(c for c in cases() if c.id == case_id)
    except StopIteration as error:
        raise KeyError(case_id) from error


def default_case():
    return "C01"
