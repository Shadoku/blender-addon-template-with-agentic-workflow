# SPDX-License-Identifier: GPL-3.0-or-later
"""Example logic: place a sequence of values at even intervals."""

from collections.abc import Sequence


def evenly_spaced(values: Sequence[float], gap: float) -> list[float]:
    """Return new coordinates so that ``values`` keep their order but sit ``gap`` apart.

    The smallest value stays where it is; everything else is laid out after it.
    Ties keep their input order (stable sort), so results are deterministic.

    >>> evenly_spaced([5.0, 0.0, 2.0], 2.0)
    [4.0, 0.0, 2.0]
    """
    if gap < 0:
        raise ValueError(f"gap must be >= 0, got {gap}")
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda i: values[i])
    start = values[order[0]]
    result = [0.0] * len(values)
    for rank, index in enumerate(order):
        result[index] = start + rank * gap
    return result
