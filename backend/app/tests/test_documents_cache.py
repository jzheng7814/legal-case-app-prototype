import tempfile
from pathlib import Path
from typing import List
from unittest import TestCase
from unittest.mock import patch

from app.data.case_document_store import JsonCaseDocumentStore
from app.schemas.documents import Document
from app.services import documents


class DocumentsCacheTests(TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._store_path = Path(self._tmpdir.name) / "case_documents.json"
        self._case_store = JsonCaseDocumentStore(self._store_path)

        # Swap in an isolated store and clear in-memory caches.
        self._original_store = documents._CASE_STORE
        documents._CASE_STORE = self._case_store
        with documents._CASE_CACHE_LOCK:
            documents._CASE_CACHE.clear()
            documents._CASE_TITLE_CACHE.clear()

    def tearDown(self) -> None:
        documents._CASE_STORE = self._original_store
        with documents._CASE_CACHE_LOCK:
            documents._CASE_CACHE.clear()
            documents._CASE_TITLE_CACHE.clear()
        self._tmpdir.cleanup()

    def _make_documents(self, count: int) -> List[Document]:
        return [
            Document(
                id=i + 1,
                title=f"Doc {i + 1}",
                type="order",
                description="desc",
                source="clearinghouse",
                content="body text",
            )
            for i in range(count)
        ]

    def test_serves_cached_documents_without_remote_fetch(self) -> None:
        case_id = "123"
        docs = self._make_documents(1)
        self._case_store.set(case_id, [doc.model_dump(mode="json") for doc in docs], "Cached Title")

        with patch.object(documents, "_fetch_remote_documents") as fetch_mock:
            result = documents.list_documents(case_id)

        fetch_mock.assert_not_called()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Doc 1")
        # Case title should be available from the cached record.
        self.assertEqual(documents.get_case_title(case_id), "Cached Title")

    def test_remote_fetch_called_once_and_warms_cache(self) -> None:
        case_id = "456"
        docs = self._make_documents(2)

        def _fake_fetch(_: str):
            # Simulate remote fetch that also persists to the store.
            self._case_store.set(case_id, [doc.model_dump(mode="json") for doc in docs], "Fetched Title")
            return docs, "Fetched Title"

        with patch.object(documents, "_fetch_remote_documents", side_effect=_fake_fetch) as fetch_mock:
            first = documents.list_documents(case_id)
            second = documents.list_documents(case_id)

        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertEqual(first[0].title, "Doc 1")
        # In-memory cache should satisfy the second request without another fetch.
        self.assertEqual(second[1].title, "Doc 2")

        stored = self._case_store.get(case_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.case_title, "Fetched Title")
