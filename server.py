from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from extraction import Input as ExtractionInput
from extraction import main as query_extraction_results_main
from main import Input as ClassificationInput
from main import main as query_classification_results_main

mcp = FastMCP("ixpy-df-mcp")


@mcp.tool()
def query_classification_results(
    batchId: str,
    entityKey: str | None = None,
    pageSize: int = 200,
) -> dict[str, Any]:
    """Query classification records from Data Fabric by batchId."""
    try:
        input_data = ClassificationInput(
            batchId=batchId,
            entityKey=entityKey,
            pageSize=pageSize,
        )
    except ValidationError as exc:
        return {"error": f"Invalid input: {exc}"}

    return query_classification_results_main(input_data)


@mcp.tool()
def query_extraction_results(
    batchId: str,
    entityKey: str | None = None,
    pageSize: int = 200,
    maxResults: int = 2000,
    maxResponseBytes: int = 2500000,
) -> dict[str, Any]:
    """Query extraction records from Data Fabric by batchId."""
    try:
        input_payload: dict[str, Any] = {
            "batchId": batchId,
            "entityKey": entityKey,
            "pageSize": pageSize,
            "maxResults": maxResults,
            "maxResponseBytes": maxResponseBytes,
        }

        input_data = ExtractionInput.model_validate(input_payload)
    except ValidationError as exc:
        return {"error": f"Invalid input: {exc}"}

    return query_extraction_results_main(input_data)


if __name__ == "__main__":
    mcp.run()
