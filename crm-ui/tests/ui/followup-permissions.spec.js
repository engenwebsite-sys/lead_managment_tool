import { expect, test } from "@playwright/test";
import { followUp, mockCrm, staff } from "./fixtures.js";

const staffUser = { ...staff, leadAccess: { MMC: false } };

async function openFollowUps(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Follow-ups", exact: true }).click();
}

test("staff without edit privileges can only change the schedule in Reschedule", async ({ page }) => {
  await mockCrm(page, {}, staffUser);
  await openFollowUps(page);
  const row = page.getByRole("row").filter({ hasText: followUp.purpose });
  await expect(row.getByRole("button", { name: /^Edit / })).toHaveCount(0);
  await expect(row.getByRole("button", { name: /^Delete / })).toHaveCount(0);
  await expect(row.getByRole("button", { name: /^Complete / })).toBeVisible();
  await expect(row.getByRole("button", { name: /^History / })).toBeVisible();
  await row.getByRole("button", { name: /^Reschedule / }).click();
  const form = page.getByRole("dialog", { name: "Reschedule follow-up" });
  await expect(form.getByLabel("Purpose *")).not.toBeEditable();
  await expect(form.getByRole("textbox", { name: "Notes", exact: true })).not.toBeEditable();
  await expect(form.getByLabel("Date & time *")).toBeEditable();
});

test("edit permission opens the prefilled follow-up form", async ({ page }) => {
  await mockCrm(page, {}, { ...staffUser, canEditFollowUps: true });
  await openFollowUps(page);
  const row = page.getByRole("row").filter({ hasText: followUp.purpose });
  await expect(row.getByRole("button", { name: /^Delete / })).toHaveCount(0);
  await row.getByRole("button", { name: /^Edit / }).click();
  const form = page.getByRole("dialog", { name: "Edit follow-up" });
  await expect(form.getByLabel("Purpose *")).toHaveValue(followUp.purpose);
  await expect(form.getByRole("textbox", { name: "Notes", exact: true })).toBeEditable();
  await expect(form.getByLabel("Reason for rescheduling *")).toHaveCount(0);
  await form.getByLabel("Date & time *").fill("2030-12-05T11:30");
  await expect(form.getByRole("textbox", { name: "Reason for rescheduling *", exact: true })).toBeVisible();
});

test("delete permission asks for confirmation and sends the current version", async ({ page }) => {
  await mockCrm(page, {}, { ...staffUser, canDeleteFollowUps: true });
  let request;
  await page.route("**/api/follow-ups/fixture-follow-up?*", async (route) => {
    request = route.request();
    await route.fulfill({ status: 204 });
  });
  await openFollowUps(page);
  const row = page.getByRole("row").filter({ hasText: followUp.purpose });
  await expect(row.getByRole("button", { name: /^Edit / })).toHaveCount(0);
  await row.getByRole("button", { name: /^Delete / }).click();
  const dialog = page.getByRole("dialog", { name: "Delete follow-up?" });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(request).toBeUndefined();
  await row.getByRole("button", { name: /^Delete / }).click();
  await dialog.getByRole("button", { name: "Delete follow-up", exact: true }).click();
  await expect(page.getByText("Follow-up archived.", { exact: true })).toBeVisible();
  expect(request.method()).toBe("DELETE");
  expect(new URL(request.url()).searchParams.get("expectedVersion")).toBe(String(followUp.version));
});
