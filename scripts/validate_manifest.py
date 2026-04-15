import json
import httpx
import sys
import os
from jsonschema import validate, ValidationError

SCHEMA_URL = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
MANIFEST_PATH = "server.json"

def validate_manifest():
    if not os.path.exists(MANIFEST_PATH):
        print(f"Error: {MANIFEST_PATH} not found.")
        sys.exit(1)

    print(f"Fetching official schema from {SCHEMA_URL}...")
    try:
        response = httpx.get(SCHEMA_URL, timeout=10.0)
        response.raise_for_status()
        schema = response.json()
    except Exception as e:
        print(f"Error fetching schema: {e}")
        sys.exit(1)

    print(f"Loading {MANIFEST_PATH}...")
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        sys.exit(1)

    print("Validating manifest...")
    try:
        validate(instance=manifest, schema=schema)
        print("Validation Successful: server.json is compliant with the MCP Registry schema.")
    except ValidationError as e:
        print("Validation Failed!")
        print(f"Message: {e.message}")
        print(f"Path: {' -> '.join(str(p) for p in e.path)}")
        sys.exit(1)

if __name__ == "__main__":
    validate_manifest()
