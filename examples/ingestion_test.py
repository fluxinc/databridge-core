import os
from morphik import Morphik
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Connect to Morphik
# When is_local is True, it defaults to http://localhost:8000
db = Morphik(is_local=True, timeout=10000)

print("Starting ingestion test...")

# Ingest a file
try:
    file_doc = db.ingest_file(
        "core/tests/integration/test_data/test.txt", metadata={"category": "test", "topic": "ingestion"}
    )
    print(f"Successfully ingested file with ID: {file_doc.external_id}")
    print("Ingestion test PASSED.")
except Exception as e:
    print(f"Ingestion test FAILED: {e}")