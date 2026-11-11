import { useRef, useState } from "react";
import { Save } from "lucide-react";
import Modal from "../Modal";
import { Button } from "../ui";
import { fromIST, istInput } from "../../lib/followUps";
import { EVENT_STATUSES, EVENT_TYPES, REMINDER_OPTIONS } from "../../lib/events";

const inputClass =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-950 outline-none placeholder:text-slate-500 focus:border-teal-600 focus:ring-2 focus:ring-teal-100";

function Field({ label, children, wide = false }) {
  return (
    <label className={`flex min-w-0 flex-col gap-2 text-xs font-semibold text-slate-800 ${wide ? "sm:col-span-2" : ""}`}>
      {label}
      {children}
    </label>
  );
}

export default function EventEditor({ record, staffUsers = [], staffError = "", onSave, onClose }) {
  const editing = Boolean(record?.id);

  const [form, setForm] = useState(() => {
    const defaultStart = Date.now() + 3600000;
    const defaultEnd = defaultStart + 3600000;
    return {
      title: record?.title || "",
      description: record?.description || "",
      event_type: record?.event_type || "Other",
      status: record?.status || "Planned",
      start_at: istInput(record?.start_at || defaultStart),
      end_at: istInput(record?.end_at || defaultEnd),
      venue: record?.venue || "",
      reminder_minutes: Array.isArray(record?.reminder_minutes) ? record.reminder_minutes : [1440, 60],
      assigned_user_ids: Array.isArray(record?.assigned_user_ids) ? record.assigned_user_ids : [],
    };
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const saveLock = useRef(false);

  function bind(name) {
    return {
      value: form[name],
      onChange: (event) => setForm((current) => ({ ...current, [name]: event.target.value })),
    };
  }

  function toggleReminder(minutes) {
    setForm((current) => {
      const exists = current.reminder_minutes.includes(minutes);
      if (!exists && current.reminder_minutes.length >= 10) return current;
      return {
        ...current,
        reminder_minutes: exists
          ? current.reminder_minutes.filter((item) => item !== minutes)
          : [...current.reminder_minutes, minutes].sort((a, b) => b - a),
      };
    });
  }

  function toggleStaff(userId) {
    setForm((current) => {
      const exists = current.assigned_user_ids.includes(userId);
      if (!exists && current.assigned_user_ids.length >= 100) return current;
      return {
        ...current,
        assigned_user_ids: exists
          ? current.assigned_user_ids.filter((id) => id !== userId)
          : [...current.assigned_user_ids, userId],
      };
    });
  }

  async function submit(event) {
    event.preventDefault();
    if (saveLock.current) return;
    saveLock.current = true;
    setSaving(true);
    setError("");

    try {
      const title = form.title.trim();
      if (title.length < 2) throw new Error("Event title must be at least 2 characters.");
      const startIso = fromIST(form.start_at);
      const endIso = fromIST(form.end_at);
      if (Date.parse(endIso) <= Date.parse(startIso)) {
        throw new Error("Event end time must be after start time.");
      }

      const payload = {
        title,
        description: form.description.trim(),
        event_type: form.event_type,
        status: form.status,
        start_at: startIso,
        end_at: endIso,
        venue: form.venue.trim(),
        reminder_minutes: form.reminder_minutes,
        assigned_user_ids: form.assigned_user_ids,
      };

      await onSave(payload, record);
    } catch (saveError) {
      setError(saveError.message || "Could not save the event.");
    } finally {
      saveLock.current = false;
      setSaving(false);
    }
  }

  return (
    <Modal title={editing ? "Edit event" : "Schedule event"} onClose={saving ? () => {} : onClose}>
      <form onSubmit={submit}>
        <fieldset disabled={saving} className="min-w-0">
          <div className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
            <p className="text-xs leading-6 text-slate-700 sm:col-span-2">
              All dates and times are in IST (Asia/Kolkata). Assigned staff cannot have overlapping active events.
            </p>

            <Field label="Event title *" wide>
              <input
                required
                minLength={2}
                maxLength={200}
                placeholder="Product workshop, client meetup, hackathon..."
                className={inputClass}
                {...bind("title")}
              />
            </Field>

            <Field label="Event type">
              <select className={inputClass} {...bind("event_type")}>
                {EVENT_TYPES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </Field>

            <Field label="Status">
              <select className={inputClass} {...bind("status")}>
                {EVENT_STATUSES.map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </Field>

            <Field label="Start date & time (IST) *">
              <input required type="datetime-local" className={inputClass} {...bind("start_at")} />
            </Field>

            <Field label="End date & time (IST) *">
              <input required type="datetime-local" className={inputClass} {...bind("end_at")} />
            </Field>

            <Field label="Venue / location" wide>
              <input
                maxLength={250}
                placeholder="Main auditorium, Zoom link, Coimbatore office..."
                className={inputClass}
                {...bind("venue")}
              />
            </Field>

            <Field label="Description" wide>
              <textarea
                rows={3}
                maxLength={5000}
                placeholder="Agenda, notes, instructions..."
                className={`${inputClass} resize-y`}
                {...bind("description")}
              />
            </Field>

            <div className="space-y-2 sm:col-span-2">
              <span className="block text-xs font-semibold text-slate-800">
                Reminders ({form.reminder_minutes.length}/10 selected)
              </span>
              <div className="flex flex-wrap gap-2">
                {REMINDER_OPTIONS.map((option) => {
                  const active = form.reminder_minutes.includes(option.value);
                  return (
                    <button
                      key={option.value}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleReminder(option.value)}
                      className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                        active
                          ? "border-teal-800 bg-teal-800 text-white"
                          : "border-slate-300 bg-white text-slate-700 hover:bg-teal-50"
                      }`}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-2 sm:col-span-2">
              <span className="block text-xs font-semibold text-slate-800">
                Assign staff ({form.assigned_user_ids.length} selected)
              </span>
              {staffError ? (
                <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">
                  Could not load staff list: {staffError}
                </p>
              ) : staffUsers.length === 0 ? (
                <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                  No active Staff accounts found. Create Staff accounts in Settings &gt; Users &amp; access to assign them here.
                </p>
              ) : (
                <div className="grid max-h-40 gap-2 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3 sm:grid-cols-2">
                  {staffUsers.map((staff) => {
                    const checked = form.assigned_user_ids.includes(staff.id);
                    return (
                      <label
                        key={staff.id}
                        className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-xs transition-colors ${
                          checked
                            ? "border-teal-600 bg-teal-50 text-teal-950"
                            : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleStaff(staff.id)}
                          className="size-4 accent-teal-800"
                        />
                        <span className="min-w-0 flex-1">
                          <strong className="block truncate font-semibold">{staff.name}</strong>
                          <small className="block truncate text-[11px] text-slate-600">{staff.email}</small>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            {error && (
              <p role="alert" className="rounded-lg bg-rose-50 p-3 text-xs text-rose-900 sm:col-span-2">
                {error}
              </p>
            )}
          </div>

          <footer className="flex justify-end gap-3 border-t border-slate-200 bg-slate-50 px-4 py-3">
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit">
              <Save size={16} />
              {saving ? "Saving..." : editing ? "Save changes" : "Create event"}
            </Button>
          </footer>
        </fieldset>
      </form>
    </Modal>
  );
}
