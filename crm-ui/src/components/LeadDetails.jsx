import { useEffect, useRef, useState } from "react";
import { Plus, Pencil, Trash2, Check, RefreshCw } from "lucide-react";
import Modal from "./Modal";
import AddLeadModal from "./AddLeadModal";
import FollowUpEditor from "./followups/FollowUpEditor";
import Pagination from "./Pagination";
import { Button } from "./ui";
import useServerPage from "../hooks/useServerPage";
import usePagination from "../hooks/usePagination";
import { getLeadById } from "../services/leadsApi";
import { getFollowUps, getFollowUpsPage, createFollowUp, updateFollowUp, deleteFollowUp } from "../services/followUpsApi";
import { formatFollowUpDate } from "../lib/followUps";
import { divisionLabel, divisions } from "../data/crm";
import { activityChanges } from "../lib/activity";

function Evidence({ entries = [], newestFirst = false }) {
  const ordered = newestFirst ? entries : [...entries].reverse();
  return <ol className="space-y-3 border-l border-teal-200 pl-3">{ordered.map((entry) => <li key={entry.id} className="text-xs leading-5">
    <p className="font-semibold text-teal-900">{formatFollowUpDate(entry.at)} IST {entry.actor && `· ${entry.actor}`}</p>
    {entry.action && <strong className="block">{entry.action}</strong>}
    <p className="whitespace-pre-wrap">{entry.message}</p>
    {activityChanges(entry).map((change) => <p key={change.field} className="break-words text-slate-600">{change.label}: {change.before} → {change.after}</p>)}
  </li>)}</ol>;
}

export default function LeadDetails({ lead: initial, user, canEdit, canDelete, startEditing = false, onClose, onUpdate, onDelete, onChanged }) {
  const [lead, setLead] = useState(initial);
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState(startEditing);
  const [editor, setEditor] = useState(null);
  const [revision, setRevision] = useState(0);
  const [view, setView] = useState("All");
  const [section, setSection] = useState("Actions");
  const [timelineResult, setTimelineResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const admin = user.role === "Admin";
  const archived = Boolean(lead.deletedAt);
  const filters = { leadId: initial.id, view, includeArchived: admin, pageSize: 20 };
  const tasks = useServerPage(getFollowUpsPage, filters, revision);
  const timelineKey = `${initial.id}:${revision}`;
  useEffect(() => {
    if (section !== "Timeline") return;
    const controller = new AbortController();
    getFollowUps({ leadId: initial.id, includeArchived: admin, signal: controller.signal }).then((items) => {
      if (!controller.signal.aborted) setTimelineResult({ key: timelineKey, items });
    }).catch((err) => { if (!controller.signal.aborted) setTimelineResult({ key: timelineKey, error: err.message }); });
    return () => controller.abort();
  }, [section, initial.id, admin, timelineKey]);
  const timelineCurrent = timelineResult?.key === timelineKey ? timelineResult : null;
  const timelineEntries = [...(lead.history || []), ...(timelineCurrent?.items || []).flatMap((item) =>
    item.history.map((event) => ({ ...event, id: `${item.id}:${event.id}`, action: `${item.purpose}${item.deletedAt ? " (archived)" : ""}` }))) ]
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at) || a.id.localeCompare(b.id));
  const timelinePage = usePagination(timelineEntries);
  useEffect(() => {
    let active = true;
    getLeadById(initial.id, { archived: Boolean(initial.deletedAt) }).then((item) => { if (active) { setLead(item); setLoaded(true); } })
      .catch((err) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [initial.id, initial.deletedAt]);
  const editTasks = admin || user.canEditFollowUps === true;
  const deleteTasks = admin || user.canDeleteFollowUps === true;
  const canSchedule = !archived && (admin || lead.assigneeUserId === user.id || tasks.rows.some((item) => !item.deletedAt));
  function changed() { setRevision((value) => value + 1); onChanged?.(); }
  async function saveAction(record, next) {
    if (record.version) await updateFollowUp(record, next); else await createFollowUp(record);
    setEditor(null); changed();
  }
  async function mutate(operation) {
    if (lock.current) return;
    lock.current = true; setSaving(true); setError("");
    try { await operation(); } catch (err) { setError(err.message); }
    finally { lock.current = false; setSaving(false); }
  }
  if (editing && loaded && !archived) return <AddLeadModal initialLead={lead} allowedDivisions={admin ? divisions : [lead.division]}
    saving={saving} saveError={error} onClose={() => setEditing(false)} onSave={(draft) => mutate(async () => {
      const updates = Object.fromEntries(Object.entries(draft).filter(([key, value]) => key !== "id" && JSON.stringify(value) !== JSON.stringify(lead[key])));
      const updated = await onUpdate(lead.id, { ...updates, expectedVersion: lead.version });
      setLead(updated); setEditing(false); changed();
    })} />;
  if (editor) return <FollowUpEditor mode={editor.mode} record={editor.record} canEditDetails={editTasks}
    onClose={() => setEditor(null)} onSave={saveAction} />;
  return <Modal title={lead.opportunityName || lead.customer} onClose={saving ? () => {} : onClose}>
    <div className="space-y-5 p-4 sm:p-5">
      <div className="rounded-xl bg-teal-50 p-4 text-sm leading-6">
        <p className="font-semibold">{lead.customer} · {divisionLabel(lead.division)}</p>
        <p>{lead.status} · {lead.priority} priority</p>
        <p className="whitespace-pre-wrap">{lead.description}</p>
        {lead.contact && <p>Contact: {lead.contact}</p>}
        {lead.contactEmail && <p className="break-all">Email: {lead.contactEmail}</p>}
        {lead.contactPhone && <p>Phone: {lead.contactPhone}</p>}
        <p>Source: {lead.leadSource}{lead.referredBy?.name && ` · ${lead.referredBy.name}`}</p>
        {archived && <p className="font-semibold text-rose-800">Archived · data and history retained</p>}
      </div>
      {error && <p role="alert" className="text-sm text-rose-800">{error}</p>}
      {!loaded && !error && <p role="status">Loading opportunity…</p>}
      <div className="flex flex-wrap gap-2">
        {canSchedule && <Button disabled={!loaded || saving} onClick={() => setEditor({ mode: "schedule", record: { leadId: lead.id, customer: lead.customer, division: lead.division, opportunityName: lead.opportunityName, referredBy: lead.referredBy, leadSource: lead.leadSource } })}><Plus size={15} />Add action</Button>}
        {canEdit && !archived && <Button variant="secondary" disabled={!loaded || saving} onClick={() => setEditing(true)}><Pencil size={15} />Edit lead</Button>}
        {canDelete && !archived && <Button variant="secondary" disabled={!loaded || saving} onClick={() => {
          if (window.confirm("Archive this opportunity? All actions and history will be retained.")) mutate(async () => { await onDelete(lead.id, lead.version); onClose(); });
        }}><Trash2 size={15} />Delete lead</Button>}
      </div>
      <details><summary className="cursor-pointer text-sm font-semibold text-teal-900">Opportunity change history</summary><div className="mt-3"><Evidence entries={lead.history} />{!lead.history?.length && <p className="text-xs">No recorded changes for this existing lead.</p>}</div></details>
      <section className="space-y-3" aria-label="Opportunity actions">
        <div className="flex gap-2">{["Actions", "Timeline"].map((name) => <button type="button" key={name} aria-pressed={section === name} onClick={() => setSection(name)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${section === name ? "bg-teal-900 text-white" : "bg-slate-100 text-slate-800"}`}>{name === "Timeline" ? "Activity timeline" : "Actions"}</button>)}</div>
        {section === "Timeline" ? <div className="space-y-3">
          <h3 className="font-semibold">Activity timeline</h3>
          {!timelineCurrent && <p role="status" className="text-xs">Loading complete activity history…</p>}
          {timelineCurrent?.error && <p role="alert" className="text-xs text-rose-800">{timelineCurrent.error} <button type="button" onClick={() => setRevision((value) => value + 1)}>Retry</button></p>}
          {timelineCurrent?.items && <><Evidence entries={timelinePage.rows} newestFirst /><Pagination pagination={timelinePage} />{!timelinePage.total && <p className="text-xs">No recorded activity yet.</p>}</>}
        </div> : <>
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">Actions &amp; history</h3><select aria-label="Action status" value={view} onChange={(event) => setView(event.target.value)} className="rounded-lg border border-slate-300 p-2 text-sm">{["All", "Today", "Overdue", "Upcoming", "Completed"].map((name) => <option key={name}>{name}</option>)}</select></div>
        <p className="text-xs text-slate-600">{tasks.total} actions · All times IST{admin ? " · Includes archived actions" : ""}</p>
        {tasks.loading && <p role="status" className="text-xs">Loading actions…</p>}
        {tasks.error && <p role="alert" className="text-xs text-rose-800">{tasks.error} <button onClick={tasks.refresh}>Retry</button></p>}
        {tasks.rows.map((item) => <article key={item.id} className="space-y-2 rounded-xl border border-slate-200 p-3 text-sm">
          <div className="flex flex-wrap items-start justify-between gap-2"><strong className="break-words">{item.purpose}</strong><span className="text-xs font-semibold text-teal-900">{item.deletedAt ? "Archived" : item.status === "Pending" ? "Open" : "Closed"}</span></div>
          <p className="text-xs">{item.type} · {formatFollowUpDate(item.dueAt)} IST · {item.assignedTo}</p>
          <p className="whitespace-pre-wrap text-xs">{item.notes}</p>
          {item.status === "Completed" && <p className="whitespace-pre-wrap text-xs">Completed {formatFollowUpDate(item.completedAt)} IST · {item.outcome}: {item.completionNotes}</p>}
          {!archived && !item.deletedAt && <div className="flex flex-wrap gap-2">
            {item.status === "Pending" && <>
              <Button variant="secondary" onClick={() => setEditor({ mode: "complete", record: item })}><Check size={14} />Complete</Button>
              <Button variant="secondary" onClick={() => setEditor({ mode: "reschedule", record: item })}><RefreshCw size={14} />Reschedule</Button>
            </>}
            {editTasks && <Button variant="secondary" onClick={() => setEditor({ mode: "edit", record: item })}><Pencil size={14} />Edit action</Button>}
            {deleteTasks && <Button variant="secondary" disabled={saving} onClick={() => { if (window.confirm(`Archive "${item.purpose}"? Its history will be retained.`)) mutate(async () => { await deleteFollowUp(item.id, item.version); changed(); }); }}><Trash2 size={14} />Delete action</Button>}
          </div>}
          <details><summary className="cursor-pointer text-xs font-semibold text-teal-900">Action history</summary><div className="mt-3"><Evidence entries={item.history} /></div></details>
        </article>)}
        {!tasks.loading && !tasks.error && !tasks.total && <p className="text-sm text-slate-600">No actions in this view.</p>}
        <Pagination pagination={tasks} />
        </>}
      </section>
    </div>
  </Modal>;
}
