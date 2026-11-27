import { useEffect, useRef, useState } from "react";
import { Plus, X } from "lucide-react";
import { divisionLabel, divisions } from "../data/crm";
import { Button, IconButton } from "./ui";
import CustomerField from "./CustomerField";
import ReferralFields from "./ReferralFields";
import { runtimeSettings } from "../lib/runtimeSettings";

const fieldClass =
    "w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-950 outline-none placeholder:text-slate-500 focus:border-teal-600 focus:ring-2 focus:ring-teal-100";

const labelClass =
    "flex min-w-0 flex-col gap-2 text-xs font-semibold text-slate-800";

export default function AddLeadModal({ onClose, onSave, saveError = "", saving = false, allowedDivisions = divisions, preferredDivision, initialLead }) {
    const preferences = runtimeSettings();
    const fixedDivision = allowedDivisions.length === 1 ? allowedDivisions[0] : null;
    const defaultDivision = [preferredDivision, preferences.workspace.defaultDivision, "nemilink"]
        .find((division) => allowedDivisions.includes(division)) ?? allowedDivisions[0];
    const dialogRef = useRef(null);
    const [customerLink, setCustomerLink] = useState({ customer: initialLead?.customer || "", customerId: initialLead?.customerId || null });
    const [error, setError] = useState("");

    useEffect(() => {
        if (!dialogRef.current.open) {
            dialogRef.current.showModal();
        }
    }, []);

    function handleSubmit(event) {
        event.preventDefault();
        if (saving) return;

        const data = new FormData(event.currentTarget);
        const customer = String(data.get("customer")).trim();
        const description = String(data.get("description")).trim();

        if (!customer || (preferences.leads.requireDescription && !description && (!initialLead || initialLead.description))) {
            setError("Enter a customer name and requirement.");
            return;
        }

        const leadSource = String(data.get("leadSource") || "Direct Enquiry");
        const needsReference = ["Referral", "Known Network"].includes(leadSource);
        const referenceId = String(data.get("referredById") || "");

        const retainedReference = initialLead?.leadSource === leadSource ? initialLead.referredBy : null;
        if (needsReference && !referenceId && !retainedReference) {
            setError("Select or add a reference contact.");
            return;
        }

        setError("");
        onSave({
            id: crypto.randomUUID(),
            customer,
            opportunityName: String(data.get("opportunityName") || "").trim(),
            customerId: customerLink.customerId,
            description,
            contact: String(data.get("contact")).trim(),
            contactEmail: String(data.get("contactEmail") || "").trim(),
            contactPhone: String(data.get("contactPhone") || "").trim(),
            division: fixedDivision || String(data.get("division")),
            priority: String(data.get("priority")),
            status: initialLead ? String(data.get("status")) : preferences.leads.defaultStatus,
            leadSource,
            referredBy: needsReference ? (referenceId ? {
                id: referenceId,
                name: String(data.get("referredByName") || ""),
                company: String(data.get("referredByCompany") || ""),
                phone: String(data.get("referredByPhone") || ""),
                email: String(data.get("referredByEmail") || ""),
            } : retainedReference) : null,
            referenceNotes: needsReference ? String(data.get("referenceNotes") || "").trim() : "",
        });
    }

    return (
        <dialog
            ref={dialogRef}
            aria-labelledby="lead-dialog-title"
            className="m-auto max-h-[94dvh] w-[calc(100%-1rem)] max-w-xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-0 text-slate-900 shadow-2xl backdrop:bg-slate-950/40 backdrop:backdrop-blur-sm"
            onCancel={(event) => {
                event.preventDefault();
                if (!saving) onClose();
            }}
            onClick={(event) => {
                if (!saving && event.target === event.currentTarget) onClose();
            }}
        >
            <div>
                <header className="flex items-start justify-between gap-4 border-b border-slate-200 p-4 sm:p-5">
                    <div>
                        <p className="text-[10px] font-bold tracking-[0.18em] text-teal-800">
                            {initialLead ? "OPPORTUNITY" : "NEW OPPORTUNITY"}
                        </p>
                        <h2
                            id="lead-dialog-title"
                            className="mt-2 text-xl font-bold text-slate-950"
                        >
                            {initialLead ? "Edit lead" : "Add a lead"}
                        </h2>
                        <p className="mt-2 text-xs leading-5 text-slate-700">
                            Start with the essentials. Build the relationship.
                        </p>
                    </div>

                    <IconButton aria-label="Close form" disabled={saving} onClick={onClose}>
                        <X size={21} />
                    </IconButton>
                </header>

                <form onSubmit={handleSubmit}>
                    <fieldset disabled={saving} className="min-w-0">
                    <div className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
                        <div className={labelClass}>
                            <span>Customer / company *</span>
                            <CustomerField {...customerLink} onChange={setCustomerLink} maxLength={120} />
                        </div>

                        <label className={labelClass}>
                            Project / opportunity name
                            <input name="opportunityName" maxLength={200} defaultValue={initialLead?.opportunityName || ""} placeholder="Billing Software, Elder Care..." className={fieldClass} />
                        </label>
                        <label className={labelClass}>
                            Contact person
                            <input
                                name="contact"
                                defaultValue={initialLead?.contact || ""}
                                required={preferences.leads.requireContact && (!initialLead || Boolean(initialLead.contact))}
                                placeholder="Customer name"
                                maxLength={150}
                                className={fieldClass}
                            />
                        </label>

                        <label className={labelClass}>
                            Contact email (optional)
                            <input name="contactEmail" type="email" maxLength={254} defaultValue={initialLead?.contactEmail || ""} placeholder="name@company.com" className={fieldClass} />
                        </label>
                        <label className={labelClass}>
                            Phone number (optional)
                            <input name="contactPhone" type="tel" maxLength={40} defaultValue={initialLead?.contactPhone || ""} placeholder="+91 98765 43210" className={fieldClass} />
                        </label>
                        <label className={labelClass}>
                            Division *
                            {fixedDivision ? <span className={fieldClass}>{divisionLabel(fixedDivision)}</span> : <select
                                name="division"
                                defaultValue={initialLead?.division || defaultDivision}
                                className={fieldClass}
                            >
                                {allowedDivisions.map((division) => (
                                    <option key={division} value={division}>{divisionLabel(division)}</option>
                                ))}
                            </select>}
                        </label>

                        <label className={labelClass}>
                            Priority *
                            <select
                                name="priority"
                                defaultValue={initialLead?.priority || preferences.leads.defaultPriority}
                                className={fieldClass}
                            >
                                <option>High</option>
                                <option>Medium</option>
                                <option>Low</option>
                            </select>
                        </label>

                        {initialLead && <label className={labelClass}>Status<select name="status" defaultValue={initialLead.status} className={fieldClass}>{["New", "In Progress", "Follow-up", "Won", "Lost"].map((name) => <option key={name}>{name}</option>)}</select></label>}
                        <ReferralFields initialSource={initialLead?.leadSource} initialReference={initialLead?.referredBy} initialNotes={initialLead?.referenceNotes} />

                        <label className={`${labelClass} sm:col-span-2`}>
                            Requirement *
                            <textarea
                                name="description"
                                defaultValue={initialLead?.description || ""}
                                placeholder="Describe the embedded, IoT or software requirement..."
                                required={preferences.leads.requireDescription && (!initialLead || Boolean(initialLead.description))}
                                rows={4}
                                maxLength={10000}
                                className={`${fieldClass} resize-y`}
                            />
                        </label>

                        {(error || saveError) && (
                            <p
                                role="alert"
                                className="text-xs font-medium text-rose-800 sm:col-span-2"
                            >
                                {error || saveError}
                            </p>
                        )}
                    </div>

                    <footer className="flex justify-end gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
                        <Button variant="secondary" onClick={onClose}>
                            Cancel
                        </Button>
                        <Button type="submit" disabled={saving}>
                            <Plus size={16} /> {saving ? "Saving..." : initialLead ? "Save lead" : "Create lead"}
                        </Button>
                    </footer>
                    </fieldset>
                </form>
            </div>
        </dialog>
    );
}
