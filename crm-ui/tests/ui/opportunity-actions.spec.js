import { expect, test } from "@playwright/test";
import { followUp, mockCrm, owner } from "./fixtures.js";

async function opportunityFixture(page, user = owner) {
  const errors = await mockCrm(page, {}, user);
  let lead = { id: "opportunity-1", customer: "Acme Manufacturing", opportunityName: "Billing Software", customerId: null,
    contact: "Ravi", contactEmail: "ravi@example.test", contactPhone: "+91 98765 43210", division: "MMC", description: "Billing software proposal", status: "In Progress", priority: "Medium",
    leadSource: "Direct Enquiry", referredBy: null, referenceNotes: "", assigneeUserId: user.id, version: 4,
    history: [], createdAt: "2026-11-01T00:00:00Z", updatedAt: "2026-11-01T00:00:00Z" };
  let actions = [{ ...followUp, id: "closed-1", leadId: lead.id, customer: lead.customer, opportunityName: lead.opportunityName,
    purpose: "Send presentation", assigneeUserId: owner.id, status: "Completed", completionNotes: "Presentation sent", outcome: "Connected",
    completedAt: "2026-11-20T10:00:00Z", history: [{ id: "old-event", at: "2026-11-20T10:00:00Z", message: "Original presentation sent" }] },
    { ...followUp, id: "pending-1", leadId: lead.id, customer: lead.customer, purpose: "Send MOM" }];
  const writes = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const list = (items) => ({ items, total: items.length, page: 1, pages: 1, pageSize: Number(url.searchParams.get("pageSize") || 100), hasMore: false });
    if (path === "/api/leads") return route.fulfill({ json: list([lead]) });
    if (path === `/api/leads/${lead.id}`) {
      if (request.method() === "PUT") {
        const body = request.postDataJSON(); writes.push({ path, body });
        lead = { ...lead, ...body, version: lead.version + 1 };
      }
      return route.fulfill({ json: lead });
    }
    if (path === "/api/follow-ups/assignees") return route.fulfill({ json: [{ id: owner.id, name: owner.name }, { id: "ajay-id", name: "Ajay" }] });
    if (path === "/api/follow-ups" && request.method() === "GET") {
      const view = url.searchParams.get("view");
      return route.fulfill({ json: list(view === "Completed" ? actions.filter((item) => item.status === "Completed") : actions) });
    }
    if (path === "/api/follow-ups" && request.method() === "POST") {
      const body = request.postDataJSON(); writes.push({ path, body });
      const item = { ...followUp, ...body, id: "new-action", customer: lead.customer, version: 1, history: [] };
      actions.push(item);
      return route.fulfill({ status: 201, json: item });
    }
    if (path === "/api/follow-ups/closed-1" && request.method() === "PUT") {
      const body = request.postDataJSON(); writes.push({ path, body });
      const previous = actions[0];
      actions[0] = { ...previous, ...body, version: previous.version + 1,
        history: [...previous.history, { id: "correction", at: "2026-11-27T10:00:00Z", message: "Completed action corrected.", changes: { completion_notes: { before: previous.completionNotes, after: body.completionNotes } } }] };
      return route.fulfill({ json: { record: actions[0], nextFollowUp: null } });
    }
    return route.fallback();
  });
  return { errors, writes };
}

async function openLead(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Leads", exact: true }).click();
  await page.getByRole("button", { name: "Acme Manufacturing", exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole("dialog", { name: "Billing Software", exact: true })).toBeVisible();
}

test("completed actions remain editable and parallel actions can be assigned independently", async ({ page }) => {
  const { errors, writes } = await opportunityFixture(page);
  await openLead(page);
  const closed = page.getByRole("article").filter({ hasText: "Send presentation" });
  await expect(closed.getByText("Closed", { exact: true })).toBeVisible();
  await closed.getByRole("button", { name: "Edit action", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Edit action", exact: true });
  await expect(edit.getByLabel("Purpose *")).toHaveValue("Send presentation");
  await expect(edit.getByText(/Staff access follows/)).toHaveCount(0);
  await edit.getByLabel("Completion notes *").fill("Revised presentation sent");
  await edit.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(closed.getByText(/Revised presentation sent/).first()).toBeVisible();
  expect(writes[0].body.status).toBe("Completed");
  expect(writes[0].body.expectedVersion).toBe(1);
  expect(writes[0].body.completedAt).toBe("2026-11-20T10:00:00Z");
  await page.getByRole("button", { name: "Add action", exact: true }).click();
  const schedule = page.getByRole("dialog", { name: "Schedule action", exact: true });
  await schedule.getByLabel("Purpose *").fill("Prepare proposal");
  await schedule.getByLabel("Assigned to", { exact: true }).selectOption("ajay-id");
  await schedule.getByRole("button", { name: "Save action", exact: true }).click();
  await expect(page.getByText("Prepare proposal", { exact: true })).toBeVisible();
  await expect(page.getByText("Send MOM", { exact: true })).toBeVisible();
  await expect(closed.getByText("Closed", { exact: true })).toBeVisible();
  expect(writes[1].body.assigneeUserId).toBe("ajay-id");
  expect(writes[1].body.leadId).toBe("opportunity-1");
  await page.getByRole("button", { name: "Activity timeline", exact: true }).click();
  await expect(page.getByText("Original presentation sent", { exact: true })).toBeVisible();
  await expect(page.getByText(/completion notes:.*Presentation sent.*Revised presentation sent/)).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("opportunity-timeline.png") });
  expect(errors).toEqual([]);
});

test("existing opportunity names and lead fields can be updated", async ({ page }) => {
  const { errors, writes } = await opportunityFixture(page);
  await openLead(page);
  await page.getByRole("button", { name: "Edit lead", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Edit lead", exact: true });
  await edit.getByLabel("Project / opportunity name", { exact: true }).fill("Elder Care");
  await edit.getByRole("button", { name: "Save lead", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Elder Care", exact: true })).toBeVisible();
  expect(writes[0].body.opportunityName).toBe("Elder Care");
  expect(writes[0].body.expectedVersion).toBe(4);
  expect(writes[0].body.customer).toBeUndefined();
  expect(errors).toEqual([]);
});

test("row background and keyboard open details while edit and contact controls remain independent", async ({ page }) => {
  const { errors, writes } = await opportunityFixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Leads", exact: true }).click();
  const row = page.getByRole("row", { name: "Open details for Acme Manufacturing · Billing Software", exact: true });
  await expect(row.getByText("ravi@example.test", { exact: true })).toBeVisible();
  await row.getByRole("cell", { name: "Billing software proposal", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Billing Software", exact: true });
  await expect(dialog.getByText("Email: ravi@example.test", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Close dialog", exact: true }).click();
  await row.focus();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Close dialog", exact: true }).click();
  await row.getByRole("button", { name: "Edit Acme Manufacturing", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Edit lead", exact: true });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(dialog.getByLabel("Contact email (optional)", { exact: true })).toHaveValue("ravi@example.test");
  await dialog.getByLabel("Contact email (optional)", { exact: true }).fill("");
  await dialog.getByLabel("Phone number (optional)", { exact: true }).fill("");
  await dialog.getByRole("button", { name: "Save lead", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Billing Software", exact: true })).toBeVisible();
  expect(writes[0].body.contactEmail).toBe("");
  expect(writes[0].body.contactPhone).toBe("");
  expect(errors).toEqual([]);
});

test("mobile opportunity view fits and Staff edit controls follow granted permissions", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const user = { ...owner, id: "staff-1", role: "Staff", isOwner: false, leadAccess: { MMC: false }, leadActions: {}, canEditFollowUps: false, canDeleteFollowUps: false };
  const { errors } = await opportunityFixture(page, user);
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  await page.getByRole("dialog", { name: "Workspace navigation", exact: true }).getByRole("button", { name: "Leads", exact: true }).click();
  await page.getByRole("article", { name: "Open details for Acme Manufacturing · Billing Software", exact: true }).getByText("Billing software proposal", { exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Billing Software", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Edit lead", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Edit action", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Delete action", exact: true })).toHaveCount(0);
  expect(await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: test.info().outputPath("opportunity-mobile.png") });
  expect(errors).toEqual([]);
});
