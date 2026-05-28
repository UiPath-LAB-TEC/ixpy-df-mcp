import os
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field
from uipath.platform import UiPath

sdk: UiPath | None = None

DEFAULT_ENTITY_KEY = os.getenv(
    "UIPATH_CLASSIFICATION_ENTITY_KEY"
)
DEFAULT_PAGE_SIZE = 200
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


class Input(BaseModel):
    batchId: str | None = Field(
        default=None,
        description="Required batch identifier used to filter classification records.",
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


class ClassificationRecord(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    id: str | None = Field(default=None, alias="Id")
    batch_id: str | None = Field(default=None, alias="batchId")
    document_id: str | None = Field(default=None, alias="documentId")
    document_type_id: str | None = Field(default=None, alias="documentTypeId")
    classification_confidence: float | None = Field(
        default=None,
        alias="classificationConfidence",
    )
    start_page: int | None = Field(default=None, alias="startPage")
    page_count: int | None = Field(default=None, alias="pageCount")
    classifier_name: str | None = Field(default=None, alias="classifierName")
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


def _extract_relation_scalar(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    for key in ("Id", "id", "Value", "value", "UUID", "uuid"):
        if key in value and not isinstance(value[key], (dict, list)):
            return value[key]

    return None


def _normalize_batch_id(value: Any) -> str | None:
    raw_value = _extract_relation_scalar(value)
    if raw_value is None:
        return None

    text = str(raw_value).strip()
    if not text:
        return None

    return "".join(char.lower() for char in text if char.isalnum())


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


def _to_output_record(record: dict[str, Any]) -> ClassificationRecord:
    batch_id_value = _extract_relation_scalar(_get_field(record, BATCH_ID_KEYS))

    return ClassificationRecord.model_validate(
        {
            "Id": _to_str(_get_field(record, ("Id",))),
            "batchId": _to_str(batch_id_value),
            "documentId": _to_str(_get_field(record, ("documentId",))),
            "documentTypeId": _to_str(_get_field(record, ("documentTypeId",))),
            "classificationConfidence": _to_float(
                _get_field(record, ("classificationConfidence",))
            ),
            "startPage": _to_int(_get_field(record, ("startPage",))),
            "pageCount": _to_int(_get_field(record, ("pageCount",))),
            "classifierName": _to_str(_get_field(record, ("classifierName",))),
            "operationId": _to_str(_get_field(record, ("operationId",))),
            "CreateTime": _to_iso8601(_get_field(record, CREATE_TIME_KEYS)),
            "UpdatedBy": _to_str(_get_field(record, ("UpdatedBy",))),
            "CreatedBy": _to_str(_get_field(record, ("CreatedBy",))),
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


def _success_response(records: list[ClassificationRecord]) -> dict[str, Any]:
    return {"results": [record.model_dump(by_alias=True) for record in records]}


def main(input_data: Input) -> dict[str, Any]:
    provided_batch_id = input_data.batchId
    batch_id = (provided_batch_id or "").strip()
    normalized_batch_id = _normalize_batch_id(batch_id)
    if not batch_id or normalized_batch_id is None:
        return _error_response(provided_batch_id)

    entity_key = (input_data.entityKey or DEFAULT_ENTITY_KEY or "").strip()
    if not entity_key:
        return _error_response(batch_id)

    raw_records = _list_all_records(
        entity_key=entity_key,
        page_size=input_data.pageSize,
    )

    matching_records = []
    for record in raw_records:
        record_dict = _record_to_dict(record)
        record_batch_id = _normalize_batch_id(_get_field(record_dict, BATCH_ID_KEYS))
        if record_batch_id == normalized_batch_id:
            matching_records.append(record_dict)

    if not matching_records:
        return _error_response(batch_id)

    matching_records.sort(
        key=lambda record: _parse_datetime(_get_field(record, CREATE_TIME_KEYS))
        or MIN_UTC_DATETIME,
        reverse=True,
    )

    return _success_response([_to_output_record(record) for record in matching_records])
