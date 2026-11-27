import { useEffect, useRef, useState } from "react";
import { Save } from "lucide-react";
import RecordPicker from "../RecordPicker";
import Modal from "../Modal";
import { Button } from "../ui";
import { formatFollowUpDate, fromIST, istInput, readStaff } from "../../lib/followUps";
import { runtimeSettings } from "../../lib/runtimeSettings";
import { useSettings } from "../../context/SettingsContext";
import { getActionAssignees } from "../../services/followUpsApi";

const inputClass = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-950 outline-none placeholder:text-slate-500 focus:border-teal-600 focus:ring-2 focus:ring-teal-100";
function Field({ label, children, wide = false }) {
  return <label className={`flex min-w-0 flex-col gap-2 text-xs font-semibold text-slate-800 ${wide ? "sm:col-span-2" : ""}`}>{label}{children}</label>;
}

export default function FollowUpEditor({ mode, record, canEditDetails, onSave, onClose }) {
  const { user } = useSettings();
  const completing = mode === "complete";
  const rescheduling = mode === "reschedule";
  const editing = mode === "edit";
  const correcting = editing && record?.status === "Completed";
  const detailsLocked = rescheduling && !canEditDetails;
  const title = completing ? "Complete action" : rescheduling ? "Reschedule action" : editing ? "Edit action" : "Schedule action";
  const [form, setForm] = useState(() => ({
    leadId: record?.leadId || "",
    purpose: record?.purpose || "", type: record?.type || "Call",
    dueAt: istInput(record?.dueAt || Date.now() + runtimeSettings().leads.followUpDays * 86400000),
    assignedTo: record?.assignedTo || readStaff()[0], priority: record?.priority || runtimeSettings().leads.defaultPriority,
    reminderMinutes: String(record?.reminderMinutes ?? runtimeSettings().notifications.reminderBefore), notes: completing ? "" : record?.notes || "",
    outcome: record?.outcome || "Connected", nextAt: "", reason: "",
    assigneeUserId: record?.assigneeUserId || "",
    completionNotes: record?.completionNotes || "", completedAt: istInput(record?.completedAt || Date.now()),
  }));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const saveLock = useRef(false);
  const [lead, setLead] = useState(null);
  const [assignmentOptions, setAssignmentOptions] = useState(null);
  const [assignmentError, setAssignmentError] = useState("");
  useEffect(() => {
    if (!form.leadId || user.role !== "Admin" || completing) return;
    const controller = new AbortController();
    getActionAssignees(form.leadId, controller.signal).then((items) => {
      if (!controller.signal.aborted) { setAssignmentOptions({ leadId: form.leadId, items }); setAssignmentError(""); }
    }).catch((error) => { if (!controller.signal.aborted) setAssignmentError(error.message); });
    return () => controller.abort();
  }, [form.leadId, user.role, completing]);
  const assignees = assignmentOptions?.leadId === form.leadId ? assignmentOptions.items : [];
  const scheduleChanging = Boolean(record && form.dueAt !== istInput(record.dueAt));
  const reasonRequired = rescheduling || (editing && !correcting && scheduleChanging);
  function bind(name) {
    return { value: form[name], onChange: (event) => setForm((current) => ({ ...current, [name]: event.target.value })) };
  }

  async function submit(event) {
    event.preventDefault();
    if (saveLock.current) return;
    saveLock.current = true;
    setSaving(true);
    try {
      if (!lead && !record) throw new Error("Select a linked customer lead.");
      const at = new Date().toISOString();
      const history = (message) => ({ id: crypto.randomUUID(), at, message });
      let updated;
      let next;
      if (completing) {
        if (!form.notes.trim()) throw new Error("Add a short discussion note.");
        updated = { ...record, status: "Completed", completedAt: at, outcome: form.outcome,
          completionNotes: form.notes.trim(), history: [...record.history,
            history(`Completed · ${form.outcome}. ${form.notes.trim()}`)] };
        if (form.nextAt) {
          const dueAt = fromIST(form.nextAt);
          if (Date.parse(dueAt) <= Date.now()) throw new Error("The next follow-up must be in the future.");
          next = { ...record, id: crypto.randomUUID(), dueAt, status: "Pending", createdAt: at,
            completedAt: null, outcome: "", completionNotes: "", notes: "",
            history: [history(`Scheduled next follow-up for ${formatFollowUpDate(dueAt)}.`)] };
        }
      } else {
        const dueAt = record && !scheduleChanging ? record.dueAt : fromIST(form.dueAt);
        if (!detailsLocked && (!form.purpose.trim() || !form.assignedTo.trim())) throw new Error("Enter the purpose and assigned staff.");
        if (reasonRequired && (!form.reason.trim() || Date.parse(dueAt) <= Date.now())) {
          throw new Error("Choose a future date and enter a reschedule reason.");
        }
        updated = detailsLocked ? { id: record.id, version: record.version, dueAt, rescheduleReason: form.reason.trim() } : { ...record, id: record?.id || crypto.randomUUID(),
          leadId: lead?.id || record.leadId, customer: lead?.customer || record.customer,
          division: lead?.division || record.division, referredBy: lead?.referredBy || record?.referredBy || null,
          leadSource: lead?.leadSource || record?.leadSource || "Not specified",
          purpose: form.purpose.trim(), type: form.type, dueAt, assignedTo: form.assignedTo.trim(),
          priority: form.priority, reminderMinutes: Number(form.reminderMinutes), notes: form.notes.trim(),
          status: correcting ? "Completed" : "Pending", createdAt: record?.createdAt || at, rescheduleReason: form.reason.trim(),
          history: [...(record?.history || []), history(rescheduling
            ? `Rescheduled from ${formatFollowUpDate(record.dueAt)} to ${formatFollowUpDate(dueAt)}. Reason: ${form.reason.trim()}`
            : `Scheduled ${form.type.toLowerCase()} for ${formatFollowUpDate(dueAt)}.`)] };
        if (!detailsLocked && user.role === "Admin" && form.assigneeUserId) updated.assigneeUserId = form.assigneeUserId;
        if (correcting) {
          updated.correctingCompleted = true;
          updated.outcome = form.outcome;
          updated.completionNotes = form.completionNotes.trim();
          updated.completedAt = form.completedAt === istInput(record.completedAt) ? record.completedAt : fromIST(form.completedAt);
        }
      }
      await onSave(updated, next);
    } catch (saveError) { setError(saveError.message || "Could not save the follow-up."); }
    finally { saveLock.current = false; setSaving(false); }
  }

  return <Modal title={title} onClose={saving ? () => {} : onClose}>
    <form onSubmit={submit}>
      <fieldset disabled={saving} className="min-w-0">
      <div className="grid gap-4 p-4 sm:p-5 sm:grid-cols-2">
        <p className="text-xs leading-6 text-slate-700 sm:col-span-2">All dates and times are in IST (Asia/Kolkata).</p>
        {completing ? <>
          <div className="rounded-xl bg-teal-50 p-4 sm:col-span-2">
            <strong className="text-sm text-teal-950">{record.customer}</strong>
            <p className="mt-1 text-xs text-slate-700">{record.purpose}</p>
          </div>
          <Field label="Call / meeting outcome">
            <select className={inputClass} {...bind("outcome")}>{["Connected", "No answer", "Requested callback", "Not interested"].map((value) => <option key={value}>{value}</option>)}</select>
          </Field>
          <Field label="Next action — optional">
            <input type="datetime-local" className={inputClass} {...bind("nextAt")} />
          </Field>
          <Field label="Discussion notes *" wide>
            <textarea required rows={4} maxLength={2000} className={`${inputClass} resize-y`} {...bind("notes")} />
          </Field>
          <p className="text-xs text-slate-700 sm:col-span-2">Completing this task does not change the lead's Won / Lost status.</p>
        </> : <>
          <div className="min-w-0 space-y-2 sm:col-span-2"><span className="block text-xs font-semibold text-slate-800">Customer / linked lead *</span>
            <RecordPicker kind="lead" value={form.leadId} name={lead?.opportunityName || record?.opportunityName || lead?.customer || record?.customer} disabled={Boolean(record)} onChange={(item) => { setLead(item); setForm((current) => ({ ...current, leadId: item.id, assigneeUserId: "" })); }} />
          </div>
          <div className="rounded-xl border border-teal-100 bg-teal-50 p-4 text-xs leading-6 sm:col-span-2">
            <strong className="text-teal-950">Referred by: {lead?.referredBy?.name || record?.referredBy?.name || "Not specified"}</strong>
            <p className="text-slate-700">{lead?.referredBy?.company || record?.referredBy?.company || lead?.leadSource || record?.leadSource || (lead ? "No referral recorded for this lead." : "Select a lead to see reference details.")}</p>
          </div>
          <Field label="Purpose *" wide><input required readOnly={detailsLocked} maxLength={200} placeholder="Quotation discussion, product demo..." className={inputClass} {...bind("purpose")} /></Field>
          <Field label="Action type"><select disabled={detailsLocked} className={inputClass} {...bind("type")}>{["Call", "Email", "Meeting", "Other"].map((value) => <option key={value}>{value}</option>)}</select></Field>
          <Field label="Date & time *"><input required type="datetime-local" className={inputClass} {...bind("dueAt")} /></Field>
          <Field label="Assigned to">
            {user.role === "Admin" ? <select aria-label="Assigned to" disabled={detailsLocked || !form.leadId} className={inputClass} {...bind("assigneeUserId")}>
              <option value="">{record?.assignedTo ? `Current: ${record.assignedTo}` : "Lead owner"}</option>
              {form.assigneeUserId && !assignees.some((item) => item.id === form.assigneeUserId) && <option value={form.assigneeUserId}>{record?.assignedTo || "Current assignee"}</option>}
              {assignees.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select> : <span className={inputClass}>{record?.assignedTo || user.name}</span>}
          </Field>
          {assignmentError && <p role="alert" className="text-xs text-rose-800 sm:col-span-2">Could not load assignment options: {assignmentError}</p>}
          <Field label="Priority"><select disabled={detailsLocked} className={inputClass} {...bind("priority")}>{["High", "Medium", "Low"].map((value) => <option key={value}>{value}</option>)}</select></Field>
          <Field label="Reminder before"><select disabled={detailsLocked} className={inputClass} {...bind("reminderMinutes")}>{[...new Set([0, 15, 30, 60, 120, Number(form.reminderMinutes)])].map((value) => <option key={value} value={value}>{value === 0 ? "At scheduled time" : `${value} minutes`}</option>)}</select></Field>
          {reasonRequired && <Field label="Reason for rescheduling *" wide><textarea required rows={2} maxLength={500} className={inputClass} {...bind("reason")} /></Field>}
          <Field label="Notes" wide><textarea readOnly={detailsLocked} rows={3} maxLength={2000} className={`${inputClass} resize-y`} {...bind("notes")} /></Field>
          {correcting && <>
            <Field label="Outcome"><select className={inputClass} {...bind("outcome")}>{["Connected", "No answer", "Requested callback", "Not interested"].map((value) => <option key={value}>{value}</option>)}</select></Field>
            <Field label="Completed date & time *"><input required type="datetime-local" className={inputClass} {...bind("completedAt")} /></Field>
            <Field label="Completion notes *" wide><textarea required rows={3} maxLength={2000} className={inputClass} {...bind("completionNotes")} /></Field>
          </>}
        </>}
        {error && <p role="alert" className="rounded-lg bg-rose-50 p-3 text-xs text-rose-900 sm:col-span-2">{error}</p>}
      </div>
      <footer className="flex justify-end gap-3 border-t border-slate-200 bg-slate-50 px-4 py-3">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button type="submit"><Save size={16} />{saving ? "Saving..." : completing ? "Complete action" : rescheduling ? "Save new schedule" : editing ? "Save changes" : "Save action"}</Button>
      </footer>
      </fieldset>
    </form>
  </Modal>;
}
