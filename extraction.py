import os
from collections import deque
from datetime import datetime, timezone
import json
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field
from uipath.platform import UiPath

sdk: UiPath | None = None

DEFAULT_ENTITY_KEY = os.getenv("UIPATH_EXTRACTION_ENTITY_KEY")
DEFAULT_PAGE_SIZE = 10
DEFAULT_MAX_RESULTS = 2000
DEFAULT_MAX_RESPONSE_BYTES = 2_500_000
MAX_PAGES = 1000
MIN_UTC_DATETIME = datetime.min.replace(tzinfo=timezone.utc)

BATCH_ID_KEYS = (
    "batchId",
)
CREATE_TIME_KEYS = (
    "CreateTime",
)
UPDATE_TIME_KEYS = (
    "UpdateTime",
)
RELATION_SCALAR_KEYS = (
    "Id",
    "id",
    "Value",
    "value",
    "UUID",
    "uuid",
    "batchId",
    "BatchId",
    "batchID",
    "BatchID",
)


class Input(BaseModel):
    batchId: str | None = Field(
        default=None,
        description="Required batch identifier used to filter extraction records.",
    )
    entityKey: str | None = Field(
        default=None,
        description="Optional Data Fabric entity key override.",
    )
    pageSize: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=1000,
        description="Data Fabric read page size.",
    )
    maxResults: int = Field(
        default=DEFAULT_MAX_RESULTS,
        ge=1,
        le=10000,
        description="Maximum number of matching records to include in response.",
    )
    maxResponseBytes: int = Field(
        default=DEFAULT_MAX_RESPONSE_BYTES,
        ge=10000,
        le=4000000,
        description=(
            "Approximate maximum serialized size of the results payload in bytes. "
            "Used to keep MCP responses below server limits."
        ),
    )


class ExtractionRecord(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    id: str | None = Field(default=None, alias="Id")
    filename: str | None = Field(default=None, alias="filename")
    document_id: str | None = Field(default=None, alias="documentId")
    document_type_id: str | None = Field(default=None, alias="documentTypeId")
    field_id: str | None = Field(default=None, alias="fieldId")
    field: str | None = Field(default=None, alias="field")
    is_missing: bool | None = Field(default=None, alias="isMissing")
    field_value: str | None = Field(default=None, alias="fieldValue")
    confidence: float | None = Field(default=None, alias="confidence")
    ocr_confidence: float | None = Field(default=None, alias="ocrConfidence")
    operator_confirmed: bool | None = Field(default=None, alias="operatorConfirmed")
    is_correct: bool | None = Field(default=None, alias="isCorrect")
    page_range: str | None = Field(default=None, alias="pageRange")
    page_count: int | None = Field(default=None, alias="pageCount")
    row_index: int | None = Field(default=None, alias="rowIndex")
    validated_field_value: str | None = Field(
        default=None,
        alias="validatedFieldValue",
    )
    column_index: int | None = Field(default=None, alias="columnIndex")
    batch_id: str | None = Field(default=None, alias="batchId")
    operation_id: str | None = Field(default=None, alias="operationId")
    create_time: str | None = Field(default=None, alias="CreateTime")
    updated_by: str | None = Field(default=None, alias="UpdatedBy")
    created_by: str | None = Field(default=None, alias="CreatedBy")
    update_time: str | None = Field(default=None, alias="UpdateTime")


def _normalize_key(key: str) -> str:
    return "".join(char.lower() for char in key if char.isalnum())


def _record_to_dict(record: Any) -> dict[str, Any]:
    if isinstance(record, BaseModel):
        return record.model_dump(by_alias=True)
    if isinstance(record, dict):
        return record
    if hasattr(record, "model_dump"):
        dumped = record.model_dump(by_alias=True)
        if isinstance(dumped, dict):
            return dumped
    if hasattr(record, "__dict__"):
        return dict(record.__dict__)
    return {}


def _get_field(record: dict[str, Any], candidates: Iterable[str]) -> Any:
    for key in candidates:
        if key in record:
            return record[key]

    normalized_record = {_normalize_key(key): value for key, value in record.items()}
    for key in candidates:
        normalized_key = _normalize_key(key)
        if normalized_key in normalized_record:
            return normalized_record[normalized_key]

    return None


def _extract_relation_scalars(value: Any) -> list[Any]:
    if not isinstance(value, (dict, list)):
        return [value]

    queue: deque[Any] = deque([value])
    candidates: list[Any] = []
    seen_nodes = 0

    while queue and seen_nodes < 1000:
        current = queue.popleft()
        seen_nodes += 1

        if isinstance(current, dict):
            for key in RELATION_SCALAR_KEYS:
                scalar = current.get(key)
                if scalar is not None and not isinstance(scalar, (dict, list)):
                    candidates.append(scalar)

            for nested in current.values():
                if isinstance(nested, (dict, list)):
                    queue.append(nested)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    queue.append(item)
                elif item is not None:
                    candidates.append(item)

    deduplicated: list[Any] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (type(candidate).__name__, str(candidate))
        if key not in seen:
            seen.add(key)
            deduplicated.append(candidate)

    return deduplicated


def _extract_relation_scalar(value: Any) -> Any:
    for candidate in _extract_relation_scalars(value):
        text = str(candidate).strip() if candidate is not None else ""
        if text:
            return candidate
    return None


def _normalize_batch_id(value: Any) -> str | None:
    raw_value = _extract_relation_scalar(value)
    if raw_value is None:
        return None

    text = str(raw_value).strip()
    if not text:
        return None

    return "".join(char.lower() for char in text if char.isalnum())


def _matches_batch_id(value: Any, expected_batch_id: str) -> bool:
    for candidate in _extract_relation_scalars(value):
        normalized_candidate = _normalize_batch_id(candidate)
        if normalized_candidate == expected_batch_id:
            return True
    return False


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        parsed_value = value.strip()
        if not parsed_value:
            return None
        if parsed_value.endswith("Z"):
            parsed_value = f"{parsed_value[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(parsed_value)
        except ValueError:
            try:
                dt = datetime.strptime(parsed_value, "%m/%d/%Y, %I:%M:%S %p")
            except ValueError:
                return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso8601(value: Any) -> str | None:
    dt = _parse_datetime(value)
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            numeric = float(str(value))
        except (TypeError, ValueError):
            return None
        if numeric.is_integer():
            return int(numeric)
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    return str(value)


def _list_all_records(entity_key: str, page_size: int) -> list[Any]:
    global sdk
    if sdk is None:
        sdk = UiPath()

    records: list[Any] = []
    start = 0

    for _ in range(MAX_PAGES):
        page = sdk.entities.list_records(
            entity_key=entity_key,
            start=start,
            limit=page_size,
        )
        if not page:
            break
        records.extend(page)
        if len(page) < page_size:
            break
        start += page_size

    return records


def _to_output_record(record: dict[str, Any]) -> ExtractionRecord:
    batch_id_value = _extract_relation_scalar(_get_field(record, BATCH_ID_KEYS))
    updated_by_value = _extract_relation_scalar(_get_field(record, ("UpdatedBy",)))
    created_by_value = _extract_relation_scalar(_get_field(record, ("CreatedBy",)))

    return ExtractionRecord.model_validate(
        {
            "Id": _to_str(_get_field(record, ("Id",))),
            "filename": _to_str(_get_field(record, ("filename",))),
            "documentId": _to_str(_get_field(record, ("documentId",))),
            "documentTypeId": _to_str(_get_field(record, ("documentTypeId",))),
            "fieldId": _to_str(_get_field(record, ("fieldId",))),
            "field": _to_str(_get_field(record, ("field",))),
            "isMissing": _to_bool(_get_field(record, ("isMissing",))),
            "fieldValue": _to_str(_get_field(record, ("fieldValue",))),
            "confidence": _to_float(_get_field(record, ("confidence",))),
            "ocrConfidence": _to_float(_get_field(record, ("ocrConfidence",))),
            "operatorConfirmed": _to_bool(_get_field(record, ("operatorConfirmed",))),
            "isCorrect": _to_bool(_get_field(record, ("isCorrect",))),
            "pageRange": _to_str(_get_field(record, ("pageRange",))),
            "pageCount": _to_int(_get_field(record, ("pageCount",))),
            "rowIndex": _to_int(_get_field(record, ("rowIndex",))),
            "validatedFieldValue": _to_str(
                _get_field(record, ("validatedFieldValue",))
            ),
            "columnIndex": _to_int(_get_field(record, ("columnIndex",))),
            "batchId": _to_str(batch_id_value),
            "operationId": _to_str(_get_field(record, ("operationId",))),
            "CreateTime": _to_iso8601(_get_field(record, CREATE_TIME_KEYS)),
            "UpdatedBy": _to_str(updated_by_value),
            "CreatedBy": _to_str(created_by_value),
            "UpdateTime": _to_iso8601(_get_field(record, UPDATE_TIME_KEYS)),
        }
    )


def _error_response(batch_id: Any) -> dict[str, str]:
    if batch_id is None:
        display_batch_id = "null"
    else:
        text = str(batch_id).strip()
        display_batch_id = text if text else "null"

    return {"error": f"No results found for batchId {display_batch_id}"}


def _success_response(records: list[ExtractionRecord]) -> dict[str, Any]:
    return {"results": [record.model_dump(by_alias=True) for record in records]}


def _json_size_bytes(value: Any) -> int:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return len(encoded)
    except (TypeError, ValueError):
        return len(str(value).encode("utf-8"))


def _build_limited_response(
    records: list[dict[str, Any]],
    max_results: int,
    max_response_bytes: int,
) -> dict[str, Any]:
    limited_results: list[dict[str, Any]] = []
    used_bytes = 2  # []
    was_truncated = False

    for record in records:
        if len(limited_results) >= max_results:
            was_truncated = True
            break

        record_size = _json_size_bytes(record)
        projected_size = used_bytes + record_size + (1 if limited_results else 0)
        if projected_size > max_response_bytes:
            was_truncated = True
            break

        limited_results.append(record)
        used_bytes = projected_size

    response: dict[str, Any] = {"results": limited_results}
    if was_truncated or len(limited_results) < len(records):
        response["meta"] = {
            "truncated": True,
            "totalMatchingRecords": len(records),
            "returnedRecords": len(limited_results),
            "maxResults": max_results,
            "maxResponseBytes": max_response_bytes,
            "approxResultsBytes": used_bytes,
        }

    return response


def main(input_data: Input) -> dict[str, Any]:
    provided_batch_id = input_data.batchId
    batch_id = (provided_batch_id or "").strip()
    normalized_batch_id = _normalize_batch_id(batch_id)
    if not batch_id or normalized_batch_id is None:
        return _error_response(provided_batch_id)

    entity_key = (input_data.entityKey or DEFAULT_ENTITY_KEY or "").strip()
    if not entity_key:
        return {
            "error": "Extraction entity key is not configured. Set "
            "UIPATH_EXTRACTION_ENTITY_KEY or pass entityKey."
        }

    raw_records = _list_all_records(
        entity_key=entity_key,
        page_size=input_data.pageSize,
    )

    matching_records = []
    for record in raw_records:
        record_dict = _record_to_dict(record)
        record_batch_value = _get_field(record_dict, BATCH_ID_KEYS)
        if _matches_batch_id(record_batch_value, normalized_batch_id):
            matching_records.append(record_dict)

    if not matching_records:
        return _error_response(batch_id)

    matching_records.sort(
        key=lambda record: _parse_datetime(_get_field(record, CREATE_TIME_KEYS))
        or MIN_UTC_DATETIME,
        reverse=True,
    )

    output_records = [
        _to_output_record(record).model_dump(by_alias=True) for record in matching_records
    ]

    return _build_limited_response(
        records=output_records,
        max_results=input_data.maxResults,
        max_response_bytes=input_data.maxResponseBytes,
    )
