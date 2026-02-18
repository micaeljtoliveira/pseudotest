"""In-place YAML configuration updates for pseudotest.

Provides two update modes for fixing match failures:

- **tolerance**: Compute and set a tolerance that covers the observed
  difference, leaving reference values unchanged.
- **reference**: Replace reference values with the calculated values,
  leaving tolerances unchanged.

Updates are applied directly to the in-memory YAML data structure
(ruamel.yaml round-trip nodes) and then flushed back to the file,
preserving comments and formatting.
"""

import logging
import math
from pathlib import Path
from typing import Any

from ruamel.yaml.scalarfloat import ScalarFloat

from pseudotest.comparator import is_number
from pseudotest.matchers import NON_UPDATABLE_KEYS, REFERENCE_KEYS
from pseudotest.test_config import yaml

# ---------------------------------------------------------------------------
# Tolerance computation
# ---------------------------------------------------------------------------


def compute_tolerance(difference: float) -> float:
    """Return a tolerance that covers *difference* with a 10 % safety margin.

    The result is rounded **up** to two significant figures so the YAML
    value stays compact and human-readable.

    >>> compute_tolerance(0.0034)
    0.0038
    >>> compute_tolerance(1.7)
    1.9
    """
    if difference == 0:
        return 0.0
    padded = difference * 1.1
    magnitude = math.floor(math.log10(padded))
    factor = 10 ** (magnitude - 1)
    raw = math.ceil(padded / factor) * factor
    ndigits = -(magnitude - 1)
    return round(raw, ndigits)


# ---------------------------------------------------------------------------
# Type casting
# ---------------------------------------------------------------------------

# Map ruamel.yaml scalar types to Python builtins.
_BUILTIN_MAP: dict[str, type] = {
    "ScalarFloat": float,
    "ScalarInt": int,
    "ScalarBoolean": bool,
}


def _cast_to_reference_type(value_str: str, reference: Any) -> Any:
    """Cast *value_str* to the Python type of *reference*.

    When *reference* is a :class:`ScalarFloat`, a new ``ScalarFloat`` is
    returned that preserves the original formatting (decimal precision,
    sign convention) so that the YAML round-trip stays clean.

    Falls back to returning *value_str* unchanged when the cast fails.
    """
    if isinstance(reference, ScalarFloat):
        return _make_scalar_float(float(value_str), reference)

    ref_type = type(reference)
    cast_type = _BUILTIN_MAP.get(ref_type.__name__, ref_type)
    try:
        return cast_type(value_str)
    except (ValueError, TypeError):
        return value_str


def _make_scalar_float(value: float, template: ScalarFloat) -> ScalarFloat:
    """Create a ``ScalarFloat`` with *value* inheriting format from *template*.

    The number of decimal places is preserved from *template*.  The
    ``_prec`` (characters before the decimal, including sign) and
    ``_width`` (total string length) are recomputed so the new number
    renders correctly regardless of how many integer digits it has.
    """
    t_prec = getattr(template, "_prec", 0)
    t_width = getattr(template, "_width", 0)
    m_lead0 = getattr(template, "_m_lead0", 0)

    # decimal_places = characters after '.' in the template representation
    decimal_places = t_width - t_prec - 1  # subtract chars-before-dot and dot

    # New prec = characters before the decimal point in the new value
    int_part = str(int(abs(value))) if abs(value) >= 1 else "0"
    new_prec = len(int_part) + (1 if value < 0 else 0)

    new_width = new_prec + 1 + decimal_places  # prec + dot + decimals

    return ScalarFloat(
        value,
        width=new_width,
        prec=new_prec,
        m_sign="-" if value < 0 else getattr(template, "_m_sign", False),
        m_lead0=m_lead0,
    )


# ---------------------------------------------------------------------------
# Per-match update application
# ---------------------------------------------------------------------------

MatchResult = tuple[int, bool, str | None, Any]
"""``(broadcast_index, success, calculated_value, param_set)``."""


def apply_match_updates(
    match_def: dict[str, Any],
    results: list[MatchResult],
    total: int,
    mode: str,
) -> bool:
    """Apply tolerance or reference updates to *match_def* for failed matches.

    Args:
        match_def: The raw YAML dict for this match entry (modified in-place).
        results: One ``(index, success, calculated_value, param_set)``
                 tuple per broadcast element.
        total: Total number of broadcast elements (``len(results)``).
        mode: ``"tolerance"`` or ``"reference"``.

    Returns:
        ``True`` if at least one update was applied.
    """
    # Skip matches explicitly marked as protected
    if match_def.get("protected", False):
        return False

    # Skip matches whose reference key is marked non-updatable
    ref_key = next((k for k in REFERENCE_KEYS if k in match_def), None)
    if ref_key in NON_UPDATABLE_KEYS:
        return False

    modified = False
    for index, success, calculated_value, param_set in results:
        # Skip passing matches and extraction failures
        if success or calculated_value is None:
            continue

        if mode == "tolerance":
            modified |= _update_tolerance(match_def, index, total, calculated_value, param_set)
        elif mode == "reference":
            modified |= _update_reference(match_def, index, total, calculated_value)

    return modified


def _update_tolerance(
    match_def: dict[str, Any],
    index: int,
    total: int,
    calculated_value: str,
    param_set: Any,
) -> bool:
    """Set or increase the ``tol`` key so the match would pass."""
    # Locate the reference key in this parameter set
    ref_key = next((k for k in REFERENCE_KEYS if k in param_set), None)
    if ref_key is None:
        return False

    reference = param_set[ref_key]

    # Tolerance only makes sense for numeric comparisons
    if not (is_number(str(reference)) and is_number(calculated_value)):
        return False

    difference = abs(float(calculated_value) - float(reference))
    if difference == 0:
        return False

    new_tol = compute_tolerance(difference)

    if total > 1:
        # Broadcast: ensure tol is a list of the right length
        if "tol" not in match_def:
            existing = param_set.get("tol", 0)
            match_def["tol"] = [existing] * total
        elif not isinstance(match_def["tol"], list):
            match_def["tol"] = [match_def["tol"]] * total
        match_def["tol"][index] = new_tol
    else:
        match_def["tol"] = new_tol

    return True


def _update_reference(
    match_def: dict[str, Any],
    index: int,
    total: int,
    calculated_value: str,
) -> bool:
    """Replace a reference value with the calculated one."""
    ref_key = next((k for k in REFERENCE_KEYS if k in match_def), None)
    if ref_key is None:
        return False

    original_ref = match_def[ref_key]

    if total > 1 and isinstance(original_ref, list):
        typed = _cast_to_reference_type(calculated_value, original_ref[index])
        match_def[ref_key][index] = typed
    else:
        typed = _cast_to_reference_type(calculated_value, original_ref)
        match_def[ref_key] = typed

    return True


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_config(data: dict[str, Any], file_path: Path) -> None:
    """Write the (modified) YAML data back to *file_path*."""
    with file_path.open("w") as fh:
        yaml.dump(data, fh)
    logging.info(f"Updated config written to {file_path}")
