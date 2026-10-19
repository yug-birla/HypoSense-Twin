"""Safe reading of an uploaded recording file (CSV or XLSX), in memory only.

Defences: size limit, extension allow-list, content signature (XLSX is a ZIP container; CSV
must be UTF-8 text without NUL bytes), row and column limits, exactly one worksheet. Every cell
is read as an object/text value; nothing is evaluated, and no formula is executed (openpyxl
reads cached values only). The original file name is never used as a path.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd

MAX_BYTES = 5_000_000
MAX_ROWS = 100_000
MAX_COLUMNS = 40
ALLOWED = (".csv", ".xlsx")
_ZIP_MAGIC = b"PK\x03\x04"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")
_MANGLED = re.compile(r"(.+)\.(\d+)")


class UploadRejected(ValueError):
    """The file cannot be read safely; the message is shown to the user."""


@dataclass(frozen=True)
class UploadedTable:
    file_name: str  # sanitised, display only
    file_type: str  # "csv" | "xlsx"
    frame: pd.DataFrame  # raw object frame, header row = columns
    n_bytes: int


def safe_display_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return _SAFE_NAME.sub("_", base)[:80] or "upload"


def read_upload(file_name: str, content: bytes) -> UploadedTable:
    name = safe_display_name(file_name)
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise UploadRejected(f"unsupported file type {ext or '(none)'}: use .csv or .xlsx")
    if not content:
        raise UploadRejected("the file is empty")
    if len(content) > MAX_BYTES:
        raise UploadRejected(f"the file exceeds {MAX_BYTES // 1_000_000} MB")
    if ext == ".xlsx":
        if not content.startswith(_ZIP_MAGIC):
            raise UploadRejected("not a valid .xlsx workbook (wrong file signature)")
        try:
            sheets = pd.read_excel(
                io.BytesIO(content), sheet_name=None, dtype=object, header=0, engine="openpyxl"
            )
        except Exception as exc:  # corrupted container, encrypted file, ...
            raise UploadRejected(f"the workbook cannot be read ({type(exc).__name__})") from exc
        if len(sheets) != 1:
            raise UploadRejected(f"expected exactly one worksheet, found {len(sheets)}")
        frame = next(iter(sheets.values()))
        kind = "xlsx"
    else:
        if b"\x00" in content:
            raise UploadRejected("not a text CSV file (binary content)")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UploadRejected("the CSV file must be UTF-8 encoded") from exc
        try:
            frame = pd.read_csv(
                io.StringIO(text), dtype=object, keep_default_na=False, na_values=[""]
            )
        except Exception as exc:
            raise UploadRejected(f"the CSV file cannot be parsed ({type(exc).__name__})") from exc
        kind = "csv"
    if frame.shape[1] == 0 or frame.shape[0] == 0:
        raise UploadRejected("the file has no data rows")
    if frame.shape[1] > MAX_COLUMNS:
        raise UploadRejected(f"too many columns ({frame.shape[1]} > {MAX_COLUMNS})")
    if frame.shape[0] > MAX_ROWS:
        raise UploadRejected(f"too many rows ({frame.shape[0]} > {MAX_ROWS})")
    if any(str(c).startswith("Unnamed:") for c in frame.columns):
        raise UploadRejected("every column needs a header in the first row")
    names = [str(c).strip() for c in frame.columns]
    mangled = [c for c in names if (m := _MANGLED.fullmatch(c)) and m.group(1) in names]
    if len(set(names)) != len(names) or mangled:  # pandas renames a repeated "x" to "x.1"
        raise UploadRejected("duplicate column headers")
    return UploadedTable(name, kind, frame, len(content))
