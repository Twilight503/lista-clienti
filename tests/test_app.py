import os
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


os.environ.setdefault("MONGO_URI", "mongodb://127.0.0.1:27017")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import app as app_module  # noqa: E402


class FakeCollection:
    """Implementarea minimă Mongo folosită de testele endpointurilor."""

    def __init__(self, doc=None):
        self.doc = deepcopy(doc)

    @staticmethod
    def _matches(doc, query):
        if doc is None:
            return False
        for key, expected in query.items():
            if isinstance(expected, dict) and "$exists" in expected:
                if (key in doc) is not bool(expected["$exists"]):
                    return False
            elif doc.get(key) != expected:
                return False
        return True

    def find_one(self, query):
        return deepcopy(self.doc) if self._matches(self.doc, query) else None

    def update_one(self, query, update, upsert=False):
        if self._matches(self.doc, query):
            if "$set" in update:
                self.doc.update(deepcopy(update["$set"]))
            return SimpleNamespace(matched_count=1, upserted_id=None)
        if upsert and self.doc is None:
            new_doc={key: deepcopy(value) for key, value in query.items() if not isinstance(value, dict)}
            new_doc.update(deepcopy(update.get("$setOnInsert", {})))
            new_doc.update(deepcopy(update.get("$set", {})))
            self.doc=new_doc
            return SimpleNamespace(matched_count=0, upserted_id=new_doc.get("_id"))
        return SimpleNamespace(matched_count=0, upserted_id=None)

    def replace_one(self, query, replacement, upsert=False):
        if self._matches(self.doc, query):
            self.doc=deepcopy(replacement)
            return SimpleNamespace(matched_count=1, upserted_id=None)
        if upsert and self.doc is None:
            self.doc=deepcopy(replacement)
            return SimpleNamespace(matched_count=0, upserted_id=self.doc.get("_id"))
        return SimpleNamespace(matched_count=0, upserted_id=None)


def future_iso(days=120):
    return (datetime.now(timezone.utc)+timedelta(days=days)).isoformat().replace("+00:00", "Z")


def archived(phone):
    return {
        "id": f"arc-{phone}",
        "phone": phone,
        "archivedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "deleteAt": future_iso(),
        "history": [],
        "assignmentsSnapshot": [],
        "clientHistory": [],
    }


class AppStateTests(unittest.TestCase):
    def setUp(self):
        self.original_collection=app_module.collection
        self.original_password=app_module.APP_PASSWORD
        self.original_size_limit=app_module.MAX_MONGO_DOCUMENT_BYTES
        app_module.APP_PASSWORD=""
        app_module.app.config.update(TESTING=True)

    def tearDown(self):
        app_module.collection=self.original_collection
        app_module.APP_PASSWORD=self.original_password
        app_module.MAX_MONGO_DOCUMENT_BYTES=self.original_size_limit

    def use_doc(self, doc=None):
        app_module.collection=FakeCollection(doc)
        return app_module.collection

    def test_initialization_is_idempotent(self):
        collection=self.use_doc()
        first=app_module.get_or_create_doc()
        second=app_module.get_or_create_doc()
        self.assertEqual(first["_rev"], 1)
        self.assertEqual(second["_rev"], 1)
        self.assertEqual(collection.doc["clients"], [])

    def test_legacy_document_without_revision_is_migrated_and_can_save(self):
        collection=self.use_doc({"_id": app_module.STATE_ID, **app_module.empty_state()})
        doc=app_module.get_or_create_doc()
        self.assertEqual(doc["_rev"], 0)

        with app_module.app.test_client() as client:
            response=client.post("/api/state", json={"rev": 0, "db": app_module.empty_state()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["rev"], 1)
        self.assertEqual(collection.doc["_rev"], 1)

    def test_revision_conflict_does_not_overwrite_state(self):
        state=app_module.empty_state()
        state.update({"_id": app_module.STATE_ID, "_rev": 7})
        collection=self.use_doc(state)
        incoming=app_module.empty_state()
        incoming["clients"]=[{"id": "new", "phone": "0711111111", "assignments": []}]
        with app_module.app.test_client() as client:
            response=client.post("/api/state", json={"rev": 6, "db": incoming})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(collection.doc["clients"], [])

    def test_archive_is_preserved_unless_explicit_shrink_is_requested(self):
        state=app_module.empty_state()
        state.update({
            "_id": app_module.STATE_ID,
            "_rev": 2,
            "archivedClients": [archived("0711111111"), archived("0722222222")],
        })
        collection=self.use_doc(state)
        incoming=app_module.empty_state()
        incoming["archivedClients"]=[archived("0711111111")]

        with app_module.app.test_client() as client:
            kept=client.post("/api/state", json={"rev": 2, "db": incoming})
            kept_phones={a["phone"] for a in collection.doc["archivedClients"]}
            shrunk=client.post("/api/state", json={
                "rev": 3,
                "db": incoming,
                "archiveGuard": {"allowArchiveShrink": True},
            })

        self.assertEqual(kept.status_code, 200)
        self.assertEqual(kept_phones, {"0711111111", "0722222222"})
        self.assertEqual(shrunk.status_code, 200)
        self.assertEqual([a["phone"] for a in collection.doc["archivedClients"]], ["0711111111"])

    def test_reactivated_phone_cannot_exist_in_active_and_archive(self):
        state=app_module.empty_state()
        state.update({"_id": app_module.STATE_ID, "_rev": 4, "archivedClients": [archived("0711111111")]})
        collection=self.use_doc(state)
        incoming=app_module.empty_state()
        incoming["clients"]=[{"id": "c1", "phone": "0711111111", "assignments": []}]
        incoming["archivedClients"]=[archived("0711111111")]
        with app_module.app.test_client() as client:
            response=client.post("/api/state", json={"rev": 4, "db": incoming})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(collection.doc["archivedClients"], [])

    def test_bson_dates_are_returned_as_plain_iso_strings(self):
        state=app_module.empty_state()
        state.update({
            "_id": app_module.STATE_ID,
            "_rev": 3,
            "createdAt": datetime.now(timezone.utc),
            "clients": [{"id": "c1", "phone": "0711111111", "createdAt": datetime.now(timezone.utc), "assignments": []}],
            "transfers": [{"id": "t1", "createdAt": datetime.now(timezone.utc), "items": [], "sourceCounter": {}}],
            "archivedClients": [{
                **archived("0722222222"),
                "archivedAt": datetime.now(timezone.utc),
                "deleteAt": datetime.now(timezone.utc)+timedelta(days=30),
            }],
        })
        self.use_doc(state)
        with app_module.app.test_client() as client:
            response=client.get("/api/state")
        payload=response.get_json()["db"]
        self.assertIsInstance(payload["createdAt"], str)
        self.assertIsInstance(payload["clients"][0]["createdAt"], str)
        self.assertIsInstance(payload["transfers"][0]["createdAt"], str)
        self.assertIsInstance(payload["archivedClients"][0]["deleteAt"], str)

    def test_reset_uses_monotonic_revision(self):
        state=app_module.empty_state()
        state.update({"_id": app_module.STATE_ID, "_rev": 11, "clients": [{"phone": "0711111111"}]})
        collection=self.use_doc(state)
        with app_module.app.test_client() as client:
            response=client.post("/api/reset", json={"confirm": "RESET", "rev": 11})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["rev"], 12)
        self.assertEqual(collection.doc["_rev"], 12)
        self.assertEqual(collection.doc["clients"], [])

    def test_api_requires_login_when_password_is_enabled(self):
        self.use_doc()
        app_module.APP_PASSWORD="secret"
        with app_module.app.test_client() as client:
            response=client.get("/api/state")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "auth_required")

    def test_index_renders_bulk_archive_controls_and_authenticated_logout(self):
        self.use_doc()
        app_module.APP_PASSWORD="secret"
        with app_module.app.test_client() as client:
            login=client.post("/login", data={"password": "secret"})
            response=client.get("/")
        self.assertEqual(login.status_code, 302)
        self.assertEqual(response.status_code, 200)
        html=response.get_data(as_text=True)
        self.assertIn('id="bulkArchiveBrownBtn"', html)
        self.assertIn('id="bulkArchiveRedBtn"', html)
        self.assertIn('class="verify-archive-actions"', html)
        self.assertNotIn('id="bulkArchiveSummary"', html)
        self.assertNotIn('bulkDeleteBrownBtn', html)
        self.assertIn('href="/logout"', html)

    def test_oversized_state_is_rejected_without_overwrite(self):
        state=app_module.empty_state()
        state.update({"_id": app_module.STATE_ID, "_rev": 1})
        collection=self.use_doc(state)
        app_module.MAX_MONGO_DOCUMENT_BYTES=300
        incoming=app_module.empty_state()
        incoming["clients"]=[{"id": "c1", "phone": "0711111111", "note": "x"*1000, "assignments": []}]
        with app_module.app.test_client() as client:
            response=client.post("/api/state", json={"rev": 1, "db": incoming})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(collection.doc["clients"], [])


if __name__ == "__main__":
    unittest.main()
