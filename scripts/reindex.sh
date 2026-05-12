#!/usr/bin/env bash
# =============================================================================
# Magezi — Re-index curriculum knowledge base into Qdrant
# =============================================================================
# Usage:
#   ./scripts/reindex.sh              # Full re-index (syllabus JSON + PDFs)
#   ./scripts/reindex.sh --check      # Check Qdrant health only
#
# Prerequisites:
#   - Qdrant running on $QDRANT_URL (default: http://localhost:6333)
#   - Python venv with sentence-transformers + qdrant-client installed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
COLLECTION="${QDRANT_COLLECTION:-magezi_curriculum}"
DENSE_MODEL="${DENSE_MODEL:-BAAI/bge-m3}"
DENSE_DIM="${DENSE_DIM:-1024}"

echo "========================================"
echo "  Magezi Knowledge Base Re-indexer"
echo "========================================"
echo "  Qdrant URL:   $QDRANT_URL"
echo "  Collection:   $COLLECTION"
echo "  Dense model:  $DENSE_MODEL"
echo "  Dense dim:    $DENSE_DIM"
echo "  Syllabus dir: $PROJECT_ROOT/knowledge-base/syllabus"
echo "========================================"

# Pre-flight: check Qdrant health
echo ""
echo "[1/3] Checking Qdrant health..."
if ! curl -sf "$QDRANT_URL/healthz" > /dev/null 2>&1; then
    echo "ERROR: Qdrant is not reachable at $QDRANT_URL"
    echo "Start it with: docker compose up qdrant"
    exit 1
fi
echo "  Qdrant is healthy."

if [ "${1:-}" = "--check" ]; then
    echo ""
    echo "Health check passed. Use without --check to re-index."
    exit 0
fi

# Index syllabus JSON files
echo ""
echo "[2/3] Indexing syllabus content..."
cd "$PROJECT_ROOT"
python -c "
import json
import os
from pathlib import Path

from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.environ.get('QDRANT_URL', 'http://localhost:6333')
COLLECTION = os.environ.get('QDRANT_COLLECTION', 'magezi_curriculum')
DENSE_DIM = int(os.environ.get('DENSE_DIM', '1024'))
DENSE_MODEL = os.environ.get('DENSE_MODEL', 'BAAI/bge-m3')

client = QdrantClient(url=QDRANT_URL, timeout=30)
encoder = SentenceTransformer(DENSE_MODEL)

# Recreate collection
try:
    client.delete_collection(COLLECTION)
except Exception:
    pass

client.create_collection(
    collection_name=COLLECTION,
    vectors_config={
        'dense': models.VectorParams(size=DENSE_DIM, distance=models.Distance.COSINE),
    },
)

syllabus_dir = Path('knowledge-base/syllabus')
point_id = 0

for json_file in sorted(syllabus_dir.glob('*.json')):
    with open(json_file) as f:
        data = json.load(f)
    subject = data.get('subject', json_file.stem)
    print(f'  Indexing {subject}...')

    for topic_group in data.get('topics', []):
        topic_name = topic_group.get('name', '')
        for topic in topic_group.get('topics', []):
            for subtopic in topic.get('subtopics', []):
                text = (
                    f'Subject: {subject.title()}\\n'
                    f'Topic: {topic_name} > {topic.get(\"name\", \"\")}\\n'
                    f'Subtopic: {subtopic.get(\"name\", \"\")}\\n'
                    f'Content: {subtopic.get(\"content\", \"\")}\\n'
                    f'Competences: {chr(10).join(subtopic.get(\"competences\", []))}'
                )
                vec = encoder.encode(text).tolist()
                client.upsert(
                    collection_name=COLLECTION,
                    points=[
                        models.PointStruct(
                            id=point_id,
                            vector={'dense': vec},
                            payload={
                                'text': text,
                                'source': f'NCDC {subject.title()} Syllabus 2025',
                                'subject': subject,
                                'topic': f'{topic_name} > {topic.get(\"name\", \"\")}',
                                'section': subtopic.get('name', ''),
                                'doc_type': 'syllabus',
                            },
                        )
                    ],
                )
                point_id += 1

print(f'  Indexed {point_id} passages total.')
"

# Verify
echo ""
echo "[3/3] Verifying index..."
curl -sf "$QDRANT_URL/collections/$COLLECTION" | python -m json.tool 2>/dev/null || echo "(install python for pretty output)"

echo ""
echo "Re-indexing complete."
