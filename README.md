# ixpy-df-mcp

`ixpy-df-mcp` is a Model Context Protocol (MCP) server for querying UiPath
Data Fabric records produced by IXP document processing workflows. It exposes
tools that fetch classification and extraction rows by `batchId`, normalize the
record shape, and return results that are easier for an MCP client or agent to
consume.

## What it does

The server is implemented in `server.py` with FastMCP and exposes two tools:

| Tool | Purpose |
| --- | --- |
| `query_classification_results` | Reads classification records from a Data Fabric entity, filters by `batchId`, sorts newest first by `CreateTime`, and returns normalized classification fields. |
| `query_extraction_results` | Reads extraction records from a Data Fabric entity, filters by `batchId`, sorts newest first by `CreateTime`, returns normalized extraction fields, and can truncate large responses. |

Both tools read records through the UiPath Python SDK. They require access to a
UiPath tenant, folder, and the Data Fabric entities that contain the IXP output.

## Prerequisites

- Python 3.12 or newer
- `uv`
- UiPath CLI (`uip`) for login, setup, and deployment workflows
- Access to the target UiPath tenant, folder, and Data Fabric entities
- `curl` and `jq` if you want to run `test_mcp.sh` against a deployed HTTP MCP
  endpoint

## Install and sync

Install the Python dependencies from `uv.lock`:

```bash
uv sync
```

If you will use `uip codedagent` commands, configure the local Python executable
for the UiPath CLI:

```bash
uip codedagent setup --force
```

Authenticate to UiPath before running commands that need cloud access:

```bash
uip login --organization "<ORG>" --tenant "<TENANT>" --output json
uip login status --output json
```

For unattended environments, use a service principal instead:

```bash
uip login --client-id "<ID>" --client-secret "<SECRET>" --base-url "<URL>" --output json
```

## Configuration

The tools need UiPath authentication plus entity keys for the Data Fabric tables.
Set these values in your shell, MCP host config, or deployment environment.

| Variable | Required | Used by | Description |
| --- | --- | --- | --- |
| `UIPATH_URL` | Yes | UiPath SDK | UiPath organization and tenant URL, for example `https://cloud.uipath.com/<org>/<tenant>`. |
| `UIPATH_FOLDER_PATH` | Yes | UiPath SDK | Orchestrator folder path that has access to the Data Fabric entities. |
| `UIPATH_CLASSIFICATION_ENTITY_KEY` | Required unless `entityKey` is passed | `query_classification_results` | Default Data Fabric entity key for classification records. |
| `UIPATH_EXTRACTION_ENTITY_KEY` | Required unless `entityKey` is passed | `query_extraction_results` | Default Data Fabric entity key for extraction records. |
| `UIPATH_ACCESS_TOKEN` | Yes for direct local runs | UiPath SDK and `test_mcp.sh` | Access token for UiPath API calls. UiPath wrappers may inject it from `uip login`; direct `uv run python server.py` runs need it in the process environment. |
| `MCP_URL` | Only for `test_mcp.sh` | Smoke test script | Deployed HTTP MCP endpoint URL. |

Example local environment:

```bash
export UIPATH_URL="https://cloud.uipath.com/<org>/<tenant>"
export UIPATH_FOLDER_PATH="Shared/<folder>"
export UIPATH_ACCESS_TOKEN="<token>"
export UIPATH_CLASSIFICATION_ENTITY_KEY="<classification-entity-key>"
export UIPATH_EXTRACTION_ENTITY_KEY="<extraction-entity-key>"
```

After `uip login`, credentials are stored in `~/.uipath/.auth`. For direct local
runs, source that file or export equivalent values before starting the server.

The included `mcp.json` shows a stdio MCP host configuration. If your host does
not activate the project virtual environment, prefer `uv run`:

```json
{
  "servers": {
    "ixpy-df-mcp": {
      "transport": "stdio",
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "env": {
        "UIPATH_URL": "https://cloud.uipath.com/<org>/<tenant>",
        "UIPATH_FOLDER_PATH": "Shared/<folder>",
        "UIPATH_ACCESS_TOKEN": "<token>",
        "UIPATH_CLASSIFICATION_ENTITY_KEY": "<classification-entity-key>",
        "UIPATH_EXTRACTION_ENTITY_KEY": "<extraction-entity-key>"
      }
    }
  }
}
```

## Run locally

Start the MCP server over stdio:

```bash
uv run python server.py
```

Most MCP clients start stdio servers themselves from their configured command,
so you normally add the server to your MCP host configuration instead of running
it directly in a terminal.

## Tool reference

### `query_classification_results`

Arguments:

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `batchId` | string | Required | Batch identifier used to filter classification records. |
| `entityKey` | string or null | `UIPATH_CLASSIFICATION_ENTITY_KEY` | Optional Data Fabric entity key override. |
| `pageSize` | integer | `200` | Data Fabric page size. Must be between 1 and 1000. |

Response:

```json
{
  "results": [
    {
      "Id": "record-id",
      "batchId": "batch-id",
      "documentId": "document-id",
      "documentTypeId": "document-type-id",
      "classificationConfidence": 0.98,
      "startPage": 1,
      "pageCount": 2,
      "classifierName": "classifier",
      "operationId": "operation-id",
      "CreateTime": "2026-05-28T18:00:00Z",
      "UpdatedBy": "user",
      "CreatedBy": "user",
      "UpdateTime": "2026-05-28T18:00:00Z"
    }
  ]
}
```

If no records are found, the tool returns:

```json
{"error": "No results found for batchId <batchId>"}
```

### `query_extraction_results`

Arguments:

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `batchId` | string | Required | Batch identifier used to filter extraction records. |
| `entityKey` | string or null | `UIPATH_EXTRACTION_ENTITY_KEY` | Optional Data Fabric entity key override. |
| `pageSize` | integer | `200` | Data Fabric page size. Must be between 1 and 1000. |
| `maxResults` | integer | `2000` | Maximum number of matching records to include. Must be between 1 and 10000. |
| `maxResponseBytes` | integer | `2500000` | Approximate maximum serialized size of the results payload. Must be between 10000 and 4000000. |

Response:

```json
{
  "results": [
    {
      "Id": "record-id",
      "filename": "invoice.pdf",
      "documentId": "document-id",
      "documentTypeId": "document-type-id",
      "fieldId": "field-id",
      "field": "InvoiceNumber",
      "isMissing": false,
      "fieldValue": "INV-1001",
      "confidence": 0.94,
      "ocrConfidence": 0.91,
      "operatorConfirmed": true,
      "isCorrect": true,
      "pageRange": "1",
      "pageCount": 1,
      "rowIndex": null,
      "validatedFieldValue": "INV-1001",
      "columnIndex": null,
      "batchId": "batch-id",
      "operationId": "operation-id",
      "CreateTime": "2026-05-28T18:00:00Z",
      "UpdatedBy": "user",
      "CreatedBy": "user",
      "UpdateTime": "2026-05-28T18:00:00Z"
    }
  ]
}
```

When `maxResults` or `maxResponseBytes` truncates the response, the tool includes
metadata:

```json
{
  "results": [],
  "meta": {
    "truncated": true,
    "totalMatchingRecords": 2500,
    "returnedRecords": 2000,
    "maxResults": 2000,
    "maxResponseBytes": 2500000,
    "approxResultsBytes": 1234567
  }
}
```

If `UIPATH_EXTRACTION_ENTITY_KEY` is not set and no `entityKey` argument is
passed, the tool returns a configuration error.

## Deploy

This repository contains UiPath project metadata (`uipath.json` and
`entry-points.json`) for packaging the MCP server. After installing dependencies,
authenticating, and configuring the project with `uip codedagent setup --force`,
deploy with one of the UiPath CLI targets:

```bash
uip codedagent deploy --my-workspace
uip codedagent deploy --tenant
uip codedagent deploy --folder "<Folder name>"
```

If a version has already been published, bump the patch version in
`pyproject.toml` before redeploying.

## Verification and smoke checks

Check that the Python modules compile:

```bash
uv run python -m py_compile server.py main.py extraction.py
```

Check that the server imports and exposes the tool functions without making a
UiPath API call:

```bash
uv run python - <<'PY'
from server import query_classification_results, query_extraction_results

print(query_classification_results(batchId=""))
print(query_extraction_results(batchId=""))
PY
```

After deploying an HTTP MCP endpoint, run the included smoke test:

```bash
export MCP_URL="https://<deployed-mcp-endpoint>"
export UIPATH_ACCESS_TOKEN="<token>"
./test_mcp.sh "<batch-id>" "<extraction-entity-key>" 100 1000000
```

The script initializes an MCP session, lists the exposed tools, and calls
`query_extraction_results`.
