import { formatFollowUpDate } from "./followUps";

function display(value, field) {
  if (value === null || value === undefined || value === "") return "Not set";
  if (Array.isArray(value)) return value.map((item) => display(item, field)).join(", ");
  if (typeof value === "object") return Object.entries(value).filter(([key]) => key !== "id")
    .map(([key, item]) => `${key.replaceAll("_", " ")}: ${display(item, key)}`).join(" · ");
  if (field.endsWith("_at") && Number.isFinite(Date.parse(value))) return `${formatFollowUpDate(value)} IST`;
  return String(value);
}

export function activityChanges(entry) {
  return Object.entries(entry.changes || {}).filter(([field]) => !field.endsWith("_id"))
    .map(([field, change]) => ({ field, label: field.replaceAll("_", " "), before: display(change.before, field), after: display(change.after, field) }));
}
