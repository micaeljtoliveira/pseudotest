"""In-place YAML configuration updates for pseudotest.

Provides three update modes:

- **tolerance**: Compute and set a tolerance that covers the observed
  difference, leaving reference values unchanged.
- **reference**: Replace reference values with the calculated values
  for *failing* matches only, leaving tolerances unchanged.
- **reference_all**: Replace reference values with the calculated values
  for *all* matches (passing and failing), leaving tolerances unchanged.

Updates are applied directly to the in-memory YAML data structure
(ruamel.yaml round-trip nodes) and then flushed back to the file,
preserving comments and formatting.
"""

import logging
import math
from pathlib import Path
from typing import Any

from ruamel.yaml.scalarbool import ScalarBoolean
from ruamel.yaml.scalarfloat import ScalarFloat

from pseudotest.comparator import get_precision_from_string_format, parse_number
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

# Strings accepted for a boolean reference.  bool() cannot be used, as bool("false") is True.
_BOOL_STRINGS: dict[str, bool] = {"true": True, "yes": True, "on": True, "false": False, "no": False, "off": False}


def cast_like(value_str: str | None, reference: Any) -> Any:
    """Cast *value_str* to the type of *reference*.

    When *reference* is a :class:`ScalarFloat`, a new ``ScalarFloat`` is
    returned that preserves the original formatting (decimal precision,
    sign convention) so that the YAML round-trip stays clean.  An integer
    reference gets an integer only when the value is integral.

    Falls back to returning *value_str* unchanged when the cast fails.
    """
    if value_str is None:
        return None

    # ruamel.yaml's ScalarBoolean subclasses int, so test it before numbers
    if isinstance(reference, bool | ScalarBoolean):
        return _BOOL_STRINGS.get(value_str.strip().lower(), value_str)

    if isinstance(reference, int | float):
        number = parse_number(value_str)
        if number is None:
            return value_str
        if isinstance(reference, ScalarFloat) and math.isfinite(number):
            return _make_scalar_float(number, reference)
        if isinstance(reference, int) and number.is_integer():
            return int(number)
        return number

    return value_str


def _make_scalar_float(value: float, template: ScalarFloat) -> ScalarFloat:
    """Create a ``ScalarFloat`` with *value* inheriting format from *template*.

    The sign follows *value*; an explicit ``+`` in *template* is kept for
    non-negative values.  A template in scientific notation keeps its
    exponent style and the width of its mantissa, which is written with one
    digit before the decimal (``0.00000000E+09`` becomes ``1.40343322E-16``),
    so no significant digit is lost.  Otherwise the number of decimal places is
    preserved from *template*, and the ``_prec`` (characters before the
    decimal, including sign) and ``_width`` (total string length) are
    recomputed so the new number renders correctly regardless of how many
    integer digits it has.
    """
    t_prec = getattr(template, "_prec", 0)
    t_width = getattr(template, "_width", 0)
    t_sign = getattr(template, "_m_sign", False)
    m_lead0 = getattr(template, "_m_lead0", 0)
    m_sign = "-" if value < 0 else ("+" if t_sign == "+" else False)

    if getattr(template, "_exp", None):
        # ruamel.yaml counts the sign in the mantissa's _prec but not in its
        # _width, so only _prec changes when the sign does.  Leading zeros in
        # the mantissa would cost digits (and break negative values).
        new_prec = t_prec - bool(t_sign) + bool(m_sign) if t_prec > 0 else t_prec
        return ScalarFloat(
            value,
            width=t_width,
            prec=new_prec,
            m_sign=m_sign,
            m_lead0=0,
            exp=template._exp,
            e_width=template._e_width,
            e_sign=template._e_sign,
        )

    # decimal_places = characters after '.' in the template representation
    decimal_places = t_width - t_prec - 1  # subtract chars-before-dot and dot

    # New prec = characters before the decimal point in the new value
    int_part = str(int(abs(value))) if abs(value) >= 1 else "0"
    new_prec = len(int_part) + (1 if m_sign else 0)

    new_width = new_prec + 1 + decimal_places  # prec + dot + decimals

    return ScalarFloat(
        value,
        width=new_width,
        prec=new_prec,
        m_sign=m_sign,
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
    """Apply tolerance or reference updates to *match_def*.

    Args:
        match_def: The raw YAML dict for this match entry (modified in-place).
        results: One ``(index, success, calculated_value, param_set)``
                 tuple per broadcast element.
        total: Total number of broadcast elements (``len(results)``).
        mode: ``"tolerance"``, ``"reference"``, or ``"reference_all"``.

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
        # Skip extraction failures; in reference_all mode also process passing matches
        if calculated_value is None or (success and mode != "reference_all"):
            continue

        if mode == "tolerance":
            modified |= _update_tolerance(match_def, index, total, calculated_value, param_set)
        elif mode in ("reference", "reference_all"):
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

    calculated = parse_number(calculated_value)
    reference = parse_number(param_set[ref_key])

    # Tolerance only makes sense for numeric comparisons
    if calculated is None or reference is None:
        return False

    difference = abs(calculated - reference)
    if not math.isfinite(difference):
        logging.warning(f"No tolerance can cover the difference between {calculated_value} and {param_set[ref_key]}")
        return False
    if difference == 0:
        # Check if the existing tolerance is smaller than the effective precision
        existing_tol = param_set.get("tol") or 0
        if not (existing_tol and existing_tol > 0):
            return False
        precision = get_precision_from_string_format(calculated_value)
        if existing_tol >= precision:
            return False
        new_tol = 0.0
    else:
        # A tolerance below the precision of the calculated value would make the match fail anyway
        new_tol = max(compute_tolerance(difference), get_precision_from_string_format(calculated_value))

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
    broadcast = total > 1 and isinstance(original_ref, list)
    reference = original_ref[index] if broadcast else original_ref

    # A numeric reference is never replaced by text, e.g. a Fortran overflow such as '***'
    if parse_number(reference) is not None and parse_number(calculated_value) is None:
        logging.warning(f"Not replacing numeric reference {reference} with non-numeric value '{calculated_value}'")
        return False

    typed = cast_like(calculated_value, reference)
    if broadcast:
        match_def[ref_key][index] = typed
    else:
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
