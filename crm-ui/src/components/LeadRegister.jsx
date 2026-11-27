import { useEffect, useState } from "react";
import LeadTable from "./LeadTable";
import { Button } from "./ui";
import useServerPage from "../hooks/useServerPage";
import { getLeadsPage } from "../services/leadsApi";
import { leadAccessFor } from "../lib/permissions";
import LeadDetails from "./LeadDetails";

export default function LeadRegister({ division, revision, user, onUpdateLead, onDeleteLead, onChanged }) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [archived, setArchived] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setQuery(search.trim()), 300); return () => clearTimeout(timer); }, [search]);
  const pagination = useServerPage(getLeadsPage, { division, q: query, archived }, revision);
  const viewAccess = leadAccessFor(user);
  const permits = (lead, action) => user.role === "Admin" ||
    (Object.hasOwn(viewAccess, lead.division) && user.leadActions?.[lead.division]?.includes(action));
  return <div className="space-y-3"><div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-700"><span>{pagination.loading ? "Loading leads..." : `${pagination.total} matching leads`}</span><Button variant="secondary" disabled={pagination.loading} onClick={pagination.refresh}>Reload leads</Button></div>
    {pagination.error && <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-900">{pagination.error}</p>}
    {user.role === "Admin" && <label className="flex items-center gap-2 text-xs text-slate-700"><input type="checkbox" checked={archived} onChange={(event) => setArchived(event.target.checked)} />Show archived opportunities</label>}
    <LeadTable leads={pagination.rows} onUpdateLead={onUpdateLead} onDeleteLead={onDeleteLead}
      onOpenLead={(lead) => setSelected({ lead })} onEditDetails={(lead) => setSelected({ lead, editing: true })}
      canEditLead={(lead) => !archived && permits(lead, "edit")} canDeleteLead={(lead) => !archived && permits(lead, "delete")}
      remote={{ pagination, search, setSearch }} />
    {selected && <LeadDetails key={selected.lead.id} lead={selected.lead} user={user} startEditing={selected.editing}
      canEdit={permits(selected.lead, "edit")} canDelete={permits(selected.lead, "delete")}
      onClose={() => setSelected(null)} onUpdate={onUpdateLead} onDelete={onDeleteLead} onChanged={() => { pagination.refresh(); onChanged?.(); }} />}
  </div>;
}
