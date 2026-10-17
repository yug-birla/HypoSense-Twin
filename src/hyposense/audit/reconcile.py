"""Reconcile measured official-data values against blueprint-reported values (S1.4).

Status rules (mechanical; nothing is classified by judgement):
- MATCH: the canonical (v5) measurement equals the blueprint value.
- EXPECTED DIFFERENCE: v5 differs, BUT a pre-v5 figshare version reproduces the blueprint value
  exactly, AND every file that differs between that version and v5 is listed in the publisher's
  v5 version note. The difference is then fully attributable to the documented data update.
- UNEXPLAINED DIFFERENCE: anything else. This blocks Gate G0 until it is investigated.
"""

from __future__ import annotations

from typing import Any

MATCH, EXPECTED, UNEXPLAINED = "MATCH", "EXPECTED DIFFERENCE", "UNEXPLAINED DIFFERENCE"


def _equal(a: Any, b: Any) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        keys = set(a) | set(b)
        return all(_equal(a.get(k, 0), b.get(k, 0)) for k in keys)
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, int | float) and isinstance(b, int | float):
        return abs(float(a) - float(b)) < 1e-9
    return bool(a == b)


def reconcile(
    reference: dict[str, Any],
    canonical: dict[str, Any],
    versions: dict[str, dict[str, Any]],
    noted_recordings: list[str],
) -> list[dict[str, Any]]:
    rows = []
    for key, ref in reference["values"].items():
        bp_value = ref["value"]
        measured = canonical.get(key)
        row: dict[str, Any] = {
            "metric": key,
            "blueprint_value": bp_value,
            "measured_v5": measured,
            "source": ref["section"],
        }
        if _equal(measured, bp_value):
            row.update(status=MATCH, explanation=None)
        else:
            reproducing = [
                v
                for v, d in versions.items()
                if _equal(d["blueprint_definitions"].get(key), bp_value)
                and set(d["files_differing_from_canonical"]) <= set(noted_recordings)
                and not d["only_in_canonical"]
                and not d["only_in_this_version"]
            ]
            if reproducing:
                diff_files = sorted(
                    set().union(
                        *(versions[v]["files_differing_from_canonical"] for v in reproducing)
                    )
                )
                row.update(
                    status=EXPECTED,
                    explanation=(
                        f"figshare {', '.join(reproducing)} reproduces the blueprint value "
                        "exactly; "
                        f"v5 differs only in {diff_files}, all listed in the publisher's v5 note"
                    ),
                )
            else:
                row.update(
                    status=UNEXPLAINED,
                    explanation="no pre-v5 version reproduces the "
                    "blueprint value under the documented-change condition",
                )
        rows.append(row)
    return rows
