import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.database import Base, get_db
from app.main import app
from app.models.user import User
from app.models.role_permissions import RolePermissions
from auth_helpers import isolate_request_limits, TEST_PASSWORD, test_password_hash


class CrmAccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'access.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        # Row-scope tests explicitly grant the module; default-deny is covered separately.
        self.accounts = [User(email=f"access{number}@example.test", name="Same Name" if number > 1 else f"Admin {number}",
                              role="Admin" if number < 2 else "Staff", quotation_access=number > 1, is_owner=number == 0,
                              admin_slot=number + 1 if number < 2 else None, password_hash=test_password_hash(),
                              lead_division={2: "MMC", 3: "ENGEN"}.get(number), can_create_leads=(number == 2)) for number in range(4)]
        self.db.add(RolePermissions(role="Staff", quotations=True))
        self.db.add_all(self.accounts)
        self.db.commit()
        app.dependency_overrides[get_db] = lambda: self.db
        isolate_request_limits(self)
        self.client = TestClient(app, headers={"X-CRM-Request": "1"})
        self.headers = []
        for user in self.accounts:
            result = self.client.post("/api/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
            self.assertEqual(result.status_code, 200)
            self.headers.append({"Authorization": "Bearer " + result.json()["accessToken"]})
        self.client.headers.update(self.headers[0])

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()
        self.directory.cleanup()

    def lead(self, name="Embedded prospect"):
        result = self.client.post("/api/leads", json={"customer": name, "division": "MMC", "description": "IoT firmware"})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def customer(self):
        result = self.client.post("/api/customers", json={"name": "Embedded prospect", "divisions": ["MMC"], "contacts": [{"phone": "1234567890"}]})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def quote(self):
        result = self.client.post("/api/quotations", json={"number": "ACCESS-001", "customer": "Embedded prospect", "division": "MMC", "date": "2026-11-05", "validUntil": "2026-12-05", "items": [{"description": "Firmware", "quantity": 1, "rate": 100, "billing": "One-time"}]})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def assign(self, module, record, target=2, headers=None):
        return self.client.put(f"/api/access/assignments/{module}/{record['id']}", json={"assigneeUserId": self.accounts[target].id if target is not None else None,
                           "expectedAssigneeUserId": record["assigneeUserId"], "expectedVersion": record["version"]}, headers=headers or self.headers[0])

    def test_staff_lists_details_updates_and_assignment_forgery(self):
        lead = self.lead()
        self.assertEqual([x["id"] for x in self.client.get("/api/leads", headers=self.headers[2]).json()], [lead["id"]])
        self.assertEqual(self.assign("leads", lead).status_code, 200)
        self.assertEqual([x["id"] for x in self.client.get("/api/leads", headers=self.headers[2]).json()], [lead["id"]])
        for method, payload in [("get", None), ("put", {"priority": "High"})]:
            kwargs = {"json": payload} if payload else {}
            self.assertEqual(getattr(self.client, method)(f"/api/leads/{lead['id']}", headers=self.headers[3], **kwargs).status_code, 404)
        self.assertEqual(self.client.put(f"/api/leads/{lead['id']}", headers=self.headers[2], json={"priority": "High", "expectedVersion": 2}).status_code, 403)
        self.assertEqual(self.client.put(f"/api/leads/{lead['id']}", headers=self.headers[2], json={"assigneeUserId": self.accounts[3].id}).status_code, 422)
        self.assertEqual(self.assign("leads", lead, headers=self.headers[2]).status_code, 403)
        self.assertNotIn("crm_actor", self.db.info)

    def test_staff_creation_is_self_assigned_and_deletions_denied(self):
        self.client.headers.update(self.headers[2])
        lead, customer, quote = self.lead(), self.customer(), self.quote()
        for module, record in [("leads", lead), ("customers", customer), ("quotations", quote)]:
            self.assertEqual(record["assigneeUserId"], self.accounts[2].id)
            self.assertEqual(self.client.get(f"/api/{module}/{record['id']}", headers=self.headers[3]).status_code, 404)
            suffix = "?expectedVersion=1" if module == "quotations" else ""
            self.assertEqual(self.client.delete(f"/api/{module}/{record['id']}" + suffix).status_code, 403)
        self.assertEqual(customer["assignedTo"], self.accounts[2].name)
        self.assertEqual(self.client.get("/api/access/assignments").status_code, 403)

    def test_admin_grants_creation_only_in_the_staff_division(self):
        payload = {"customer": "New prospect", "division": "ENGEN", "description": "Firmware"}
        account = self.client.post("/api/users", json={"name": "Chan", "email": "chan@example.test",
                                   "password": TEST_PASSWORD, "leadDivision": "ENGEN"})
        self.assertEqual(account.status_code, 201, account.text)
        self.assertFalse(account.json()["canCreateLeads"])
        path = "/api/users/" + account.json()["id"]

        def sign_in():
            result = self.client.post("/api/auth/login", json={"email": "chan@example.test", "password": TEST_PASSWORD})
            self.assertEqual(result.json()["user"]["leadDivision"], "ENGEN")
            return {"Authorization": "Bearer " + result.json()["accessToken"]}

        staff = sign_in()
        other = self.lead()
        visible = self.client.post("/api/leads", json=payload)
        self.assertEqual(visible.status_code, 201, visible.text)
        self.assertEqual([row["id"] for row in self.client.get("/api/leads", headers=staff).json()], [visible.json()["id"]])
        self.assertEqual(self.client.get("/api/leads?division=MMC", headers=staff).json(), [])
        self.assertEqual(self.client.get("/api/leads/" + other["id"], headers=staff).status_code, 404)
        self.assertEqual(self.client.get("/api/workspace/overview", headers=staff).json()["metrics"]["leads"]["total"], 1)
        self.assertEqual(len(self.client.get("/api/reports/leads", headers=staff).json()["rows"]), 1)
        self.assertEqual(self.client.post("/api/leads", headers=staff, json=payload).status_code, 403)
        self.assertEqual(self.client.put(path, headers=staff, json={"expectedVersion": 1, "canCreateLeads": True}).status_code, 403)
        grant = self.client.put(path, json={"expectedVersion": 1, "canCreateLeads": True})
        self.assertEqual(grant.status_code, 200, grant.text)
        self.assertEqual(self.client.get("/api/leads", headers=staff).status_code, 401)
        staff = sign_in()
        self.assertEqual(self.client.post("/api/leads", headers=staff, json={**payload, "division": "MMC"}).status_code, 403)
        self.assertEqual(self.client.post("/api/leads", headers=staff, json=payload).status_code, 201)

    def test_staff_can_view_three_divisions_and_add_in_only_one(self):
        access = {"ENGEN": True, "nemilink": False, "ClearCode Labs": False}
        payload = {"customer": "New prospect", "description": "Firmware"}
        account = self.client.post("/api/users", json={
            "name": "Chan", "email": "multi@example.test", "password": TEST_PASSWORD, "leadAccess": access,
        })
        self.assertEqual(account.status_code, 201, account.text)
        self.assertEqual(account.json()["leadAccess"], access)
        login = self.client.post("/api/auth/login", json={"email": "multi@example.test", "password": TEST_PASSWORD})
        self.assertEqual(login.json()["user"]["leadAccess"], access)
        staff = {"Authorization": "Bearer " + login.json()["accessToken"]}
        for division in [*access, "MMC"]:
            lead = self.client.post("/api/leads", json={**payload, "division": division})
            self.assertEqual(lead.status_code, 201, lead.text)
            detail = self.client.get(f"/api/leads/{lead.json()['id']}", headers=staff)
            self.assertEqual(detail.status_code, 200 if division in access else 404)
            created = self.client.post("/api/leads", headers=staff, json={**payload, "division": division})
            self.assertEqual(created.status_code, 201 if access.get(division) else 403)
        rows = self.client.get("/api/leads", headers=staff).json()
        self.assertEqual({row["division"] for row in rows}, set(access))
        self.assertEqual(self.client.get("/api/workspace/overview", headers=staff).json()["metrics"]["leads"]["total"], 4)
        path = "/api/users/" + account.json()["id"]
        updated = self.client.put(path, json={"expectedVersion": 1, "leadAccess": {"ENGEN": False}})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["leadAccess"], {"ENGEN": False})
        self.assertEqual(self.client.get("/api/leads", headers=staff).status_code, 401)

    def test_staff_lead_edit_and_delete_grants_are_division_scoped(self):
        created = self.client.post("/api/users", json={
            "name": "Lead Staff", "email": "lead-actions@example.test", "password": TEST_PASSWORD,
            "leadAccess": {"MMC": False, "ENGEN": False},
            "leadActions": {"MMC": ["edit"], "ENGEN": ["delete"]},
        })
        self.assertEqual(created.status_code, 201, created.text)
        account_path = "/api/users/" + created.json()["id"]
        login = self.client.post("/api/auth/login", json={"email": "lead-actions@example.test", "password": TEST_PASSWORD})
        self.assertEqual(login.json()["user"]["leadActions"], {"MMC": ["edit"], "ENGEN": ["delete"]})
        staff = {"Authorization": "Bearer " + login.json()["accessToken"]}
        mmc = "/api/leads/" + self.lead()["id"]
        engen = "/api/leads/" + self.client.post("/api/leads", json={
            "customer": "ENGEN prospect", "division": "ENGEN", "description": "Engineering",
        }).json()["id"]
        other = "/api/leads/" + self.client.post("/api/leads", json={
            "customer": "Other prospect", "division": "nemilink", "description": "Engineering",
        }).json()["id"]
        self.assertEqual(self.client.put(mmc, headers=staff, json={"expectedVersion": 1, "division": "ENGEN"}).status_code, 403)
        self.assertEqual(self.client.put(mmc, headers=staff, json={"expectedVersion": 1, "priority": "High"}).status_code, 200)
        self.assertEqual(self.client.delete(mmc + "?expectedVersion=2", headers=staff).status_code, 403)
        self.assertEqual(self.client.put(engen, headers=staff, json={"expectedVersion": 1, "priority": "High"}).status_code, 403)
        self.assertEqual(self.client.delete(other + "?expectedVersion=1", headers=staff).status_code, 404)
        self.assertEqual(self.client.delete(engen + "?expectedVersion=1", headers=staff).status_code, 204)
        orphaned = self.client.put(account_path, json={"expectedVersion": 1, "leadActions": {"nemilink": ["edit"]}})
        self.assertEqual(orphaned.status_code, 422)
        saved = self.client.put(account_path, json={"expectedVersion": 1, "leadAccess": {"ENGEN": False}})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["leadActions"], {"ENGEN": ["delete"]})
        self.assertEqual(self.client.get(engen, headers=staff).status_code, 401)

    def test_new_self_assigned_actions_keep_their_independent_owner(self):
        lead = self.lead()
        self.assign("leads", lead)
        result = self.client.post("/api/follow-ups", headers=self.headers[2], json={"leadId": lead["id"], "purpose": "Call", "dueAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "assignedTo": "Someone else"})
        self.assertEqual(result.status_code, 201, result.text)
        task = result.json()
        self.assertEqual(task["assignedTo"], self.accounts[2].name)
        for path in ["/api/follow-ups", "/api/follow-ups/upcoming", "/api/follow-ups/overdue"]:
            self.assertEqual(self.client.get(path, headers=self.headers[3]).json(), [])
        self.assertEqual(self.client.put(f"/api/follow-ups/{task['id']}", headers=self.headers[3], json={"notes": "Hacked"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/follow-ups/{task['id']}", headers=self.headers[2]).status_code, 403)
        current = {**lead, "assigneeUserId": self.accounts[2].id, "version": 2}
        self.assertEqual(self.assign("leads", current, 3).status_code, 200)
        self.assertEqual(self.client.get(f"/api/follow-ups/{task['id']}", headers=self.headers[2]).status_code, 200)
        self.assertEqual(self.client.get(f"/api/follow-ups/{task['id']}", headers=self.headers[3]).status_code, 404)
        self.assertEqual(self.client.post("/api/follow-ups", headers=self.headers[2], json={"leadId": lead["id"], "purpose": "Call", "dueAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}).status_code, 201)

    def test_parallel_opportunity_actions_have_independent_scoped_assignees(self):
        self.accounts[3].lead_division_access = {"MMC": False}
        self.db.commit()
        lead = self.lead()
        due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        tasks = []
        for index, staff in enumerate(self.accounts[2:]):
            result = self.client.post("/api/follow-ups", json={"leadId": lead["id"], "purpose": ["Send presentation", "Prepare proposal"][index],
                "dueAt": due, "assigneeUserId": staff.id, "assignedTo": "Forged display label"})
            self.assertEqual(result.status_code, 201, result.text)
            tasks.append(result.json())
            self.assertEqual(result.json()["assignedTo"], staff.name)
        for index in range(2):
            headers = self.headers[index + 2]
            rows = self.client.get("/api/follow-ups", headers=headers).json()
            self.assertEqual([row["id"] for row in rows], [tasks[index]["id"]])
            self.assertEqual(self.client.get(f"/api/follow-ups/{tasks[1-index]['id']}", headers=headers).status_code, 404)
            self.assertEqual(self.client.put(f"/api/follow-ups/{tasks[index]['id']}", headers=headers, json={"expectedVersion": 1, "assigneeUserId": self.accounts[3-index].id}).status_code, 403)
            metrics = self.client.get("/api/workspace/metrics", headers=headers).json()
            self.assertEqual(metrics["followUps"]["All"], 1)
        filtered = self.client.get("/api/follow-ups", params={"assigneeUserId": self.accounts[3].id}).json()
        self.assertEqual([row["id"] for row in filtered], [tasks[1]["id"]])
        self.accounts[3].lead_division_access = {"ENGEN": False}
        self.db.commit()
        self.assertEqual(self.client.get("/api/follow-ups", headers=self.headers[3]).json(), [])
        denied = self.client.post("/api/follow-ups", json={"leadId": lead["id"], "purpose": "Invalid", "dueAt": due, "assigneeUserId": self.accounts[3].id})
        self.assertEqual(denied.status_code, 422)
        choices = self.client.get("/api/follow-ups/assignees", params={"leadId": lead["id"]}).json()
        self.assertNotIn(self.accounts[3].id, {item["id"] for item in choices})

    def test_completed_action_corrections_require_edit_grant_and_preserve_evidence(self):
        lead = self.lead()
        task = self.client.post("/api/follow-ups", json={"leadId": lead["id"], "purpose": "Send presentation",
            "dueAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "assigneeUserId": self.accounts[2].id}).json()
        path = f"/api/follow-ups/{task['id']}"
        completed = self.client.put(path, headers=self.headers[2], json={"expectedVersion": 1, "status": "Completed", "outcome": "Connected", "completionNotes": "Presentation sent"})
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(self.client.put(path, headers=self.headers[2], json={"expectedVersion": 2, "completionNotes": "Corrected"}).status_code, 403)
        self.accounts[2].can_edit_follow_ups = True
        self.db.commit()
        corrected = self.client.put(path, headers=self.headers[2], json={"expectedVersion": 2, "purpose": "Send revised presentation", "completionNotes": "Revised presentation sent"})
        self.assertEqual(corrected.status_code, 200, corrected.text)
        record = corrected.json()["record"]
        self.assertEqual(record["status"], "Completed")
        self.assertEqual(record["completedAt"], completed.json()["record"]["completedAt"])
        self.assertEqual(record["history"][-1]["changes"]["completion_notes"]["before"], "Presentation sent")
        self.assertEqual(len(self.client.get("/api/follow-ups").json()), 1)
        self.assertEqual(self.client.put(path, json={"expectedVersion": 2, "notes": "stale"}).status_code, 409)
        self.assertEqual(self.client.put(path, json={"expectedVersion": 3, "status": "Pending"}).status_code, 409)

    def test_existing_lead_can_be_named_and_archived_without_losing_actions(self):
        from app.models.lead import Lead
        from app.models.follow_up import FollowUp
        lead = self.lead()
        path = f"/api/leads/{lead['id']}"
        task = self.client.post("/api/follow-ups", json={"leadId": lead["id"], "purpose": "Send MOM",
            "dueAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}).json()
        saved = self.client.put(path, json={"expectedVersion": 1, "opportunityName": "Billing Software"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["history"][-1]["changes"]["opportunity_name"]["before"], "")
        self.assertEqual(self.client.get("/api/follow-ups").json()[0]["opportunityName"], "Billing Software")
        self.assertEqual(self.client.delete(path + "?expectedVersion=2").status_code, 204)
        self.assertIsNotNone(self.db.get(Lead, lead["id"]))
        self.assertIsNotNone(self.db.get(FollowUp, task["id"]))
        self.assertEqual(self.client.get("/api/leads").json(), [])
        self.assertEqual(self.client.get("/api/follow-ups").json(), [])
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get(path + "?archived=true").json()["opportunityName"], "Billing Software")
        self.assertEqual(len(self.client.get("/api/leads?archived=true").json()), 1)
        self.assertEqual(len(self.client.get("/api/follow-ups", params={"leadId": lead["id"], "includeArchived": True}).json()), 1)
        self.assertEqual(self.client.get("/api/leads?archived=true", headers=self.headers[2]).status_code, 403)
        self.assertEqual(self.client.get("/api/follow-ups?includeArchived=true", headers=self.headers[2]).status_code, 403)
        self.assertEqual(self.client.get("/api/workspace/metrics").json()["leads"]["total"], 0)
        self.assertEqual(self.client.get("/api/reports/leads").json()["rows"], [])

    def test_optional_contact_details_validate_search_and_preserve_existing_fields(self):
        lead = self.lead()
        self.assertEqual(lead["contactEmail"], "")
        self.assertEqual(lead["contactPhone"], "")
        path = f"/api/leads/{lead['id']}"
        invalid = self.client.put(path, json={"expectedVersion": 1, "contactEmail": "invalid"})
        self.assertEqual(invalid.status_code, 422)
        saved = self.client.put(path, json={"expectedVersion": 1, "contactEmail": "  sales@example.test  ", "contactPhone": "+91 98765 43210"})
        self.assertEqual(saved.status_code, 200, saved.text)
        record = saved.json()
        self.assertEqual(record["contactEmail"], "sales@example.test")
        self.assertEqual(record["customer"], lead["customer"])
        self.assertEqual(record["description"], lead["description"])
        self.assertEqual(record["history"][-1]["changes"]["contact_phone"]["before"], "")
        for query in ("sales@example.test", "98765"):
            self.assertEqual([item["id"] for item in self.client.get("/api/leads", params={"q": query}).json()], [lead["id"]])
            self.assertEqual(self.client.get("/api/leads", params={"q": query}, headers=self.headers[3]).json(), [])
        self.assertEqual(self.client.put(path, headers=self.headers[2], json={"expectedVersion": 2, "contactPhone": "Other"}).status_code, 403)
        cleared = self.client.put(path, json={"expectedVersion": 2, "contactEmail": "", "contactPhone": ""})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(cleared.json()["history"][-1]["changes"]["contact_email"]["before"], "sales@example.test")

    def test_legacy_action_assignment_still_follows_lead_owner(self):
        lead = self.lead()
        self.assign("leads", lead)
        task = self.client.post("/api/follow-ups", json={"leadId": lead["id"], "purpose": "Legacy action",
            "dueAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}).json()
        from app.models.follow_up import FollowUp
        self.assertIsNone(self.db.get(FollowUp, task["id"]).assignee_user_id)
        corrected = self.client.put(f"/api/follow-ups/{task['id']}", json={"expectedVersion": 1, "notes": "Updated legacy notes"})
        self.assertEqual(corrected.status_code, 200, corrected.text)
        self.assertIsNone(corrected.json()["record"]["assigneeUserId"])
        self.assertIsNone(self.db.get(FollowUp, task["id"]).assignee_user_id)
        self.assertEqual(self.client.get(f"/api/follow-ups/{task['id']}", headers=self.headers[2]).status_code, 200)
        self.accounts[3].lead_division_access = {"MMC": False}
        self.db.commit()
        reassigned = self.assign("leads", {**lead, "version": 2, "assigneeUserId": self.accounts[2].id}, 3)
        self.assertEqual(reassigned.status_code, 200, reassigned.text)
        self.assertEqual(self.client.get(f"/api/follow-ups/{task['id']}", headers=self.headers[2]).status_code, 404)
        self.assertEqual(self.client.get(f"/api/follow-ups/{task['id']}", headers=self.headers[3]).status_code, 200)

    def test_follow_up_permissions_are_independent_and_keep_lead_scope(self):
        staff_account = self.accounts[2]
        lead = self.lead()
        self.assertEqual(self.assign("leads", lead).status_code, 200)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        created = self.client.post("/api/follow-ups", json={
            "leadId": lead["id"], "purpose": "Review quote", "dueAt": future.isoformat(),
        })
        self.assertEqual(created.status_code, 201, created.text)
        path = f"/api/follow-ups/{created.json()['id']}"
        account_path = f"/api/users/{staff_account.id}"
        headers = self.headers[2]
        reschedule = {"expectedVersion": 1, "dueAt": (future + timedelta(days=1)).isoformat(), "rescheduleReason": "Client requested another date"}
        self.assertEqual(self.client.put(path, headers=headers, json={**reschedule, "purpose": "Denied"}).status_code, 403)
        self.assertEqual(self.client.put(path, headers=headers, json=reschedule).status_code, 200)
        self.assertEqual(self.client.put(account_path, headers=headers, json={
            "expectedVersion": 1, "canEditFollowUps": True,
        }).status_code, 403)

        def grant(version, **permissions):
            saved = self.client.put(account_path, json={"expectedVersion": version, **permissions})
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertEqual(self.client.get(path, headers=headers).status_code, 401)
            login = self.client.post("/api/auth/login", json={"email": staff_account.email, "password": TEST_PASSWORD})
            self.assertEqual(login.status_code, 200, login.text)
            self.assertEqual({key: login.json()["user"][key] for key in permissions}, permissions)
            return {"Authorization": "Bearer " + login.json()["accessToken"]}

        headers = grant(1, canEditFollowUps=True)
        self.assertEqual(self.client.put(path, headers=headers, json={"expectedVersion": 2, "notes": "Updated"}).status_code, 200)
        self.assertEqual(self.client.delete(path + "?expectedVersion=3", headers=headers).status_code, 403)

        headers = grant(2, canEditFollowUps=False, canDeleteFollowUps=True)
        self.assertEqual(self.client.put(path, headers=headers, json={"expectedVersion": 3, "notes": "Denied"}).status_code, 403)
        another_lead = self.lead("Unassigned lead")
        other = self.client.post("/api/follow-ups", json={
            "leadId": another_lead["id"], "purpose": "Other", "dueAt": future.isoformat(),
        }).json()
        self.assertEqual(self.client.delete(f"/api/follow-ups/{other['id']}?expectedVersion=1", headers=headers).status_code, 404)
        self.assertEqual(self.client.delete(path + "?expectedVersion=2", headers=headers).status_code, 409)
        self.assertEqual(self.client.delete(path + "?expectedVersion=3", headers=headers).status_code, 204)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get(f"/api/leads/{lead['id']}").status_code, 200)

    def test_quote_pdf_versions_and_customer_profiles_do_not_leak_by_name(self):
        lead, customer, quote = self.lead(), self.customer(), self.quote()
        self.assign("leads", lead)
        self.assertEqual(self.client.get("/api/customers", headers=self.headers[2]).json(), [])
        self.assertEqual(self.client.get("/api/quotations", headers=self.headers[2]).json(), [])
        for path in [f"/api/customers/{customer['id']}", f"/api/quotations/{quote['id']}", f"/api/quotations/{quote['id']}/pdf", quote["versions"][0]["pdfPath"]]:
            self.assertEqual(self.client.get(path, headers=self.headers[2]).status_code, 404)
        self.assign("customers", customer)
        self.assign("quotations", quote)
        self.assertEqual(self.client.get(f"/api/customers/{customer['id']}", headers=self.headers[2]).status_code, 200)
        self.assertEqual(self.client.get(quote["versions"][0]["pdfPath"], headers=self.headers[2]).status_code, 200)
        self.assertEqual(self.client.get(quote["versions"][0]["pdfPath"], headers=self.headers[3]).status_code, 404)
        self.assertEqual(self.client.put(f"/api/quotations/{quote['id']}", headers=self.headers[3], json={"expectedVersion": 2, "status": "Sent"}).status_code, 404)

    def test_reports_and_summary_only_count_accessible_records(self):
        lead, quote = self.lead(), self.quote()
        self.assign("leads", lead)
        self.assign("quotations", quote)
        for number, total in [(2, 1), (3, 0), (0, 1), (1, 1)]:
            report = self.client.get("/api/reports/summary", headers=self.headers[number]).json()
            self.assertEqual(report["totals"]["totalLeads"], total)
            self.assertEqual(report["totals"]["totalQuotations"], total)
            for path in ["leads", "sales"]:
                self.assertEqual(len(self.client.get("/api/reports/" + path, headers=self.headers[number]).json()["rows"]), total)

    def test_quotation_history_uses_each_revisions_original_division(self):
        quote = self.quote()
        path = f"/api/quotations/{quote['id']}"
        original_pdf = quote["versions"][0]["pdfPath"]
        revised = self.client.put(path, json={"expectedVersion": quote["version"], "document": {
            "number": quote["number"], "customer": quote["customer"], "division": "ENGEN",
            "date": "2026-11-05", "validUntil": "2026-12-05",
            "items": [{"description": "Revised scope", "quantity": 1, "rate": 100}],
        }})
        self.assertEqual(revised.status_code, 200, revised.text)
        updated = revised.json()
        self.assertEqual(len(updated["versions"]), 2)
        self.assertEqual(self.assign("quotations", updated, target=3).status_code, 200)

        staff = self.headers[3]
        detail = self.client.get(path, headers=staff).json()
        visible_pdf = updated["versions"][-1]["pdfPath"]
        self.assertEqual([row["pdfPath"] for row in detail["versions"]], [visible_pdf])
        summary = self.client.get("/api/quotations?paged=true&summary=true", headers=staff).json()["items"][0]
        self.assertEqual(summary["versionCount"], 1)
        self.assertEqual(summary["versions"][0]["pdfPath"], visible_pdf)
        self.assertEqual(self.client.get(original_pdf, headers=staff).status_code, 404)
        self.assertEqual(self.client.get(visible_pdf, headers=staff).status_code, 200)
        self.assertEqual(self.client.get(path + "/pdf", headers=staff).status_code, 200)
        self.assertEqual(self.client.get(original_pdf).status_code, 200)

    def test_removing_last_division_closes_customer_and_quotation_access(self):
        customer = self.customer()
        quote = self.quote()
        self.assertEqual(self.assign("customers", customer).status_code, 200)
        self.assertEqual(self.assign("quotations", quote).status_code, 200)
        account = self.accounts[2]
        saved = self.client.put(f"/api/users/{account.id}", json={"expectedVersion": account.version, "leadAccess": {}})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.get("/api/customers", headers=self.headers[2]).status_code, 401)
        login = self.client.post("/api/auth/login", json={"email": account.email, "password": TEST_PASSWORD})
        self.assertEqual(login.status_code, 200, login.text)
        staff = {"Authorization": "Bearer " + login.json()["accessToken"]}
        for module, record in [("customers", customer), ("quotations", quote)]:
            self.assertEqual(self.client.get(f"/api/{module}", headers=staff).json(), [])
            self.assertEqual(self.client.get(f"/api/{module}/{record['id']}", headers=staff).status_code, 404)
        self.assertEqual(self.client.put(f"/api/customers/{customer['id']}", headers=staff,
                                         json={"expectedVersion": 2, "notes": "Denied"}).status_code, 404)
        self.assertEqual(self.client.put(f"/api/quotations/{quote['id']}", headers=staff,
                                         json={"expectedVersion": 2, "status": "Sent"}).status_code, 404)
        self.assertEqual(self.client.get(quote["versions"][0]["pdfPath"], headers=staff).status_code, 404)
        self.assertEqual(self.client.post("/api/customers", headers=staff,
                                          json={"name": "Denied", "divisions": ["MMC"], "contacts": [{"phone": "1234567890"}]}).status_code, 403)
        self.assertEqual(self.client.post("/api/quotations", headers=staff, json={
            "number": "DENIED", "customer": "Denied", "division": "MMC", "date": "2026-11-05",
            "items": [{"description": "Item", "quantity": 1, "rate": 100}],
        }).status_code, 403)

    def test_staff_customer_edits_preserve_other_divisions_and_reject_new_ones(self):
        payload = {"name": "Shared customer", "divisions": ["MMC", "ENGEN"], "contacts": [{"phone": "1234567890"}]}
        created = self.client.post("/api/customers", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        customer = created.json()
        self.assertEqual(self.assign("customers", customer).status_code, 200)
        staff = self.headers[2]
        path = f"/api/customers/{customer['id']}"
        self.assertEqual(self.client.get(path, headers=staff).json()["divisions"], ["MMC"])
        self.assertEqual(self.client.get("/api/customers?division=ENGEN", headers=staff).json(), [])
        self.assertEqual(self.client.post("/api/customers", headers=staff, json=payload).status_code, 403)
        self.assertEqual(self.client.put(path, headers=staff,
                                         json={"expectedVersion": 2, "divisions": ["MMC", "Visotonics"]}).status_code, 403)
        saved = self.client.put(path, headers=staff, json={"expectedVersion": 2, "divisions": ["MMC"], "notes": "Updated"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["divisions"], ["MMC"])
        self.assertEqual(self.client.get(path).json()["divisions"], ["MMC", "ENGEN"])

    def test_admin_reassignment_conflicts_inactive_users_and_unassignment(self):
        lead = self.lead()
        self.assertEqual(self.assign("leads", lead, headers=self.headers[1]).status_code, 200)
        self.assertEqual(self.assign("leads", lead, 3).status_code, 409)
        current = {**lead, "assigneeUserId": self.accounts[2].id, "version": 2}
        self.accounts[3].is_active = False
        self.db.commit()
        self.assertEqual(self.assign("leads", current, 3).status_code, 422)
        self.assertEqual(self.assign("leads", current, None).status_code, 200)
        self.assertEqual([row["id"] for row in self.client.get("/api/leads", headers=self.headers[2]).json()], [lead["id"]])
        self.assertEqual(len(self.client.get("/api/leads", headers=self.headers[1]).json()), 1)
        self.assertEqual(self.client.get("/api/access/assignments?limit=101").status_code, 422)
        directory = self.client.get("/api/access/assignments").json()
        self.assertNotIn("email", directory["users"][0])
