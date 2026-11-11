import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Eye,
  MapPin,
  Pencil,
  Plus,
  Search,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import {
  createEvent,
  deleteEvent,
  getEvents,
  getUpcomingEvents,
  updateEvent,
  updateEventAttendance,
} from "../services/eventsApi";
import { getUsers } from "../services/usersApi";
import { Avatar, Button, Card, CardHeading, EmptyState, IconButton } from "../components/ui";
import Modal from "../components/Modal";
import EventEditor from "../components/events/EventEditor";
import { EVENT_STATUSES, EVENT_TYPES, REMINDER_OPTIONS } from "../lib/events";
import { displayDate } from "../lib/runtimeSettings";

const selectClass =
  "rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-900 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100";

const STATUS_BADGE = {
  Planned: "bg-teal-50 text-teal-900",
  Ongoing: "bg-amber-50 text-amber-900",
  Completed: "bg-emerald-50 text-emerald-900",
  Cancelled: "bg-rose-100 text-rose-900",
};

const ATTENDANCE_OPTIONS = ["Pending", "Accepted", "Declined"];

const REMINDER_LABELS = Object.fromEntries(REMINDER_OPTIONS.map((item) => [item.value, item.label]));

function formatDateTime(value) {
  return displayDate(value, true);
}

export default function Events({ user }) {
  const isAdmin = user?.role === "Admin";

  const [events, setEvents] = useState([]);
  const [upcoming, setUpcoming] = useState([]);
  const [staffUsers, setStaffUsers] = useState([]);
  const [staffError, setStaffError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [statusFilter, setStatusFilter] = useState("All");
  const [typeFilter, setTypeFilter] = useState("All");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [search, setSearch] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const [editorState, setEditorState] = useState(null);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [attendanceBusyId, setAttendanceBusyId] = useState("");
  const [attendanceMap, setAttendanceMap] = useState({});

  const staffById = useMemo(
    () => Object.fromEntries(staffUsers.map((item) => [item.id, item])),
    [staffUsers]
  );

  const loadEvents = () => {
    setLoading(true);
    setError("");
    setRefreshKey((value) => value + 1);
  };

  useEffect(() => {
    if (startDate && endDate && endDate < startDate) {
      return;
    }
    let active = true;
    const filters = {};
    if (statusFilter !== "All") filters.status = statusFilter;
    if (startDate) filters.start_date = `${startDate}T00:00:00+05:30`;
    if (endDate) filters.end_date = `${endDate}T23:59:59+05:30`;

    Promise.all([getEvents(filters), getUpcomingEvents(5)])
      .then(([allRows, upcomingRows]) => {
        if (!active) return;
        setEvents(Array.isArray(allRows) ? allRows : []);
        setUpcoming(Array.isArray(upcomingRows) ? upcomingRows : []);
        setError("");
      })
      .catch((loadError) => {
        if (active) setError(loadError.message || "Could not load events.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [statusFilter, startDate, endDate, refreshKey]);

  const dateRangeInvalid = Boolean(startDate && endDate && endDate < startDate);

  useEffect(() => {
    if (!isAdmin) return;
    let active = true;
    getUsers()
      .then((directory) => {
        if (!active) return;
        const activeStaff = (directory?.users || []).filter(
          (item) => item.role === "Staff" && item.isActive
        );
        setStaffUsers(activeStaff);
        setStaffError("");
      })
      .catch((loadError) => {
        if (active) setStaffError(loadError.message || "Could not load staff accounts.");
      });
    return () => {
      active = false;
    };
  }, [isAdmin]);

  const visibleEvents = useMemo(() => {
    const query = search.trim().toLowerCase();
    return events.filter((item) => {
      if (typeFilter !== "All" && item.event_type !== typeFilter) return false;
      if (!query) return true;
      return [item.title, item.venue, item.description, item.event_type]
        .filter(Boolean)
        .some((field) => field.toLowerCase().includes(query));
    });
  }, [events, typeFilter, search]);

  const counts = useMemo(() => {
    const base = { All: events.length, Planned: 0, Ongoing: 0, Completed: 0, Cancelled: 0 };
    for (const item of events) {
      if (Object.hasOwn(base, item.status)) base[item.status] += 1;
    }
    return base;
  }, [events]);

  async function handleSave(payload, existing) {
    if (existing?.id) {
      await updateEvent(existing.id, payload);
      setNotice(`Updated "${payload.title}" at ${new Date().toLocaleTimeString()}.`);
    } else {
      await createEvent(payload);
      setNotice(`Scheduled "${payload.title}" at ${new Date().toLocaleTimeString()}.`);
    }
    setEditorState(null);
    await loadEvents();
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setError("");
    try {
      await deleteEvent(deleteTarget.id);
      setNotice(`Deleted "${deleteTarget.title}".`);
      if (selectedEvent?.id === deleteTarget.id) setSelectedEvent(null);
      setDeleteTarget(null);
      await loadEvents();
    } catch (deleteError) {
      setError(deleteError.message || "Could not delete event.");
    } finally {
      setDeleting(false);
    }
  }

  async function handleAttendance(eventItem, statusValue) {
    setAttendanceBusyId(eventItem.id);
    setError("");
    try {
      await updateEventAttendance(eventItem.id, statusValue);
      setAttendanceMap((current) => ({ ...current, [eventItem.id]: statusValue }));
      setNotice(`Attendance for "${eventItem.title}" updated to ${statusValue}.`);
    } catch (attendanceError) {
      setError(attendanceError.message || "Could not update attendance.");
    } finally {
      setAttendanceBusyId("");
    }
  }

  function renderAssignees(eventItem) {
    const ids = eventItem.assigned_user_ids || [];
    if (!ids.length) return "Unassigned";
    if (!isAdmin) {
      return ids.includes(user?.id) ? `You + ${Math.max(0, ids.length - 1)} more` : `${ids.length} staff`;
    }
    const names = ids.map((id) => staffById[id]?.name).filter(Boolean);
    if (!names.length) return `${ids.length} staff`;
    if (names.length <= 2) return names.join(", ");
    return `${names.slice(0, 2).join(", ")} +${names.length - 2}`;
  }

  const summaryCards = [
    { name: "All", label: "Total events", icon: CalendarDays, tone: "bg-teal-50 text-teal-800", caption: "Matching current date range" },
    { name: "Planned", label: "Planned", icon: Clock3, tone: "bg-lime-100 text-lime-900", caption: "Scheduled upcoming sessions" },
    { name: "Ongoing", label: "Ongoing", icon: CalendarClock, tone: "bg-amber-50 text-amber-800", caption: "Currently in progress" },
    { name: "Completed", label: "Completed", icon: CheckCircle2, tone: "bg-emerald-50 text-emerald-800", caption: "Finished events" },
  ];

  const hasFilters = Boolean(search || typeFilter !== "All" || statusFilter !== "All" || startDate || endDate);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="max-w-xl text-xs leading-6 text-slate-700">
          {isAdmin
            ? "Schedule workshops, hackathons, trainings and meetings. Assign staff without double-booking."
            : "View events assigned to you and confirm your attendance."}
          <br />
          All times are IST · Synced with the CRM database.
        </p>
        {isAdmin && (
          <Button onClick={() => setEditorState({ mode: "create" })}>
            <Plus size={17} />
            Schedule event
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {summaryCards.map(({ name, label, icon: Icon, tone, caption }) => (
          <button
            key={name}
            type="button"
            onClick={() => setStatusFilter(name)}
            aria-pressed={statusFilter === name}
            className={`rounded-2xl border bg-white p-4 text-left shadow-sm shadow-slate-900/8 transition-shadow duration-200 hover:shadow-md focus-visible:outline-2 focus-visible:outline-teal-700 ${
              statusFilter === name ? "border-teal-600 ring-1 ring-teal-600" : "border-slate-200"
            }`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-slate-700">{label}</span>
              <span className={`flex size-9 items-center justify-center rounded-xl ${tone}`}>
                <Icon size={18} />
              </span>
            </span>
            <strong className="mt-2 block text-2xl font-bold text-slate-950">
              {loading ? "…" : counts[name] ?? 0}
            </strong>
            <span className="mt-2 block text-[11px] leading-5 text-slate-600">{caption}</span>
          </button>
        ))}
      </div>

      {upcoming.length > 0 && (
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-teal-900">
              Next upcoming events
            </h2>
            <span className="text-[11px] font-medium text-slate-600">
              {upcoming.length} planned
            </span>
          </div>
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
            {upcoming.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedEvent(item)}
                className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-left transition-colors hover:border-teal-300 hover:bg-teal-50/50"
              >
                <span className="inline-block rounded-md bg-teal-100 px-2 py-0.5 text-[10px] font-semibold text-teal-950">
                  {item.event_type}
                </span>
                <strong className="mt-2 block truncate text-xs font-bold text-slate-950" title={item.title}>
                  {item.title}
                </strong>
                <p className="mt-1 text-[11px] font-medium text-teal-900">
                  {formatDateTime(item.start_at)}
                </p>
                {item.venue && (
                  <p className="mt-1 truncate text-[11px] text-slate-600">{item.venue}</p>
                )}
              </button>
            ))}
          </div>
        </Card>
      )}

      {dateRangeInvalid && (
        <p role="alert" className="rounded-xl bg-rose-50 p-4 text-sm text-rose-900">
          End date must be on or after start date.
        </p>
      )}
      {error && !dateRangeInvalid && (
        <p role="alert" className="rounded-xl bg-rose-50 p-4 text-sm text-rose-900">
          {error}{" "}
          <button type="button" className="ml-2 font-semibold underline" onClick={loadEvents}>
            Retry
          </button>
        </p>
      )}
      {loading && !dateRangeInvalid && (
        <p role="status" className="rounded-xl bg-teal-50 p-3 text-xs text-teal-950">
          Loading event schedule from the database...
        </p>
      )}
      {notice && (
        <p role="status" className="rounded-xl border border-teal-200 bg-teal-50 p-4 text-xs text-teal-950">
          {notice}
        </p>
      )}

      <Card>
        <CardHeading
          title="Event schedule"
          description="Planned, ongoing and past events with venue, timing and staff assignments."
        />

        <div className="flex flex-wrap gap-2 border-y border-slate-100 px-5 py-3" aria-label="Event status views">
          {["All", ...EVENT_STATUSES].map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={statusFilter === name}
              onClick={() => setStatusFilter(name)}
              className={`rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
                statusFilter === name ? "bg-teal-900 text-white" : "text-slate-700 hover:bg-teal-50"
              }`}
            >
              {name}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-3 px-4 py-3">
          <label className="flex min-w-0 flex-1 basis-full items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-slate-700 focus-within:ring-2 focus-within:ring-teal-100 sm:basis-44">
            <Search size={16} />
            <input
              aria-label="Search events"
              placeholder="Title, venue or description..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-full bg-transparent text-xs outline-none placeholder:text-slate-500"
            />
          </label>

          <select
            aria-label="Filter events by type"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className={selectClass}
          >
            <option value="All">All event types</option>
            {EVENT_TYPES.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>

          <input
            aria-label="Filter events from date"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className={selectClass}
          />

          <input
            aria-label="Filter events to date"
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className={selectClass}
          />

          {hasFilters && (
            <Button
              variant="secondary"
              onClick={() => {
                setSearch("");
                setTypeFilter("All");
                setStatusFilter("All");
                setStartDate("");
                setEndDate("");
              }}
            >
              Clear filters
            </Button>
          )}
        </div>

        {/* Mobile Cards */}
        <div className="grid gap-3 px-3 pb-3 sm:grid-cols-2 lg:hidden">
          {visibleEvents.map((item) => {
            const canEdit = isAdmin && item.status !== "Completed" && item.status !== "Cancelled";
            const isAssigned = (item.assigned_user_ids || []).includes(user?.id);
            const myAttendance = attendanceMap[item.id];

            return (
              <article
                key={item.id}
                className="min-w-0 rounded-xl border border-slate-200 bg-white p-3 shadow-sm shadow-slate-900/5"
              >
                <div className="flex items-start gap-2.5">
                  <Avatar name={item.title} />
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => setSelectedEvent(item)}
                      className="break-words text-left text-xs font-bold text-slate-950 hover:text-teal-800"
                    >
                      {item.title}
                    </button>
                    <p className="mt-1 text-[11px] text-slate-700">{item.event_type}</p>
                  </div>
                  <span
                    className={`shrink-0 rounded-md px-2 py-1 text-[10px] font-semibold ${
                      STATUS_BADGE[item.status] || "bg-slate-100 text-slate-800"
                    }`}
                  >
                    {item.status}
                  </span>
                </div>

                <div className="mt-3 space-y-1.5 text-[11px] text-slate-700">
                  <p className="flex items-start gap-2">
                    <CalendarClock size={14} className="mt-0.5 shrink-0 text-teal-800" />
                    <span>
                      {formatDateTime(item.start_at)} – {formatDateTime(item.end_at)} IST
                    </span>
                  </p>
                  {item.venue && (
                    <p className="flex items-start gap-2">
                      <MapPin size={14} className="mt-0.5 shrink-0 text-slate-500" />
                      <span className="break-words">{item.venue}</span>
                    </p>
                  )}
                  <p className="flex items-start gap-2">
                    <Users size={14} className="mt-0.5 shrink-0 text-slate-500" />
                    <span>{renderAssignees(item)}</span>
                  </p>
                </div>

                {isAssigned && item.status !== "Cancelled" && (
                  <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-2">
                    <span className="text-[11px] font-semibold text-slate-700">Attendance:</span>
                    {ATTENDANCE_OPTIONS.map((option) => (
                      <button
                        key={option}
                        type="button"
                        disabled={attendanceBusyId === item.id}
                        onClick={() => handleAttendance(item, option)}
                        className={`rounded-md border px-2 py-1 text-[10px] font-semibold transition-colors ${
                          myAttendance === option
                            ? "border-teal-800 bg-teal-800 text-white"
                            : "border-slate-300 bg-white text-slate-700 hover:bg-teal-50"
                        }`}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                )}

                <div className="mt-3 flex items-center justify-end gap-1 border-t border-slate-100 pt-2">
                  <IconButton aria-label={`View ${item.title}`} onClick={() => setSelectedEvent(item)}>
                    <Eye size={16} />
                  </IconButton>
                  {canEdit && (
                    <IconButton
                      aria-label={`Edit ${item.title}`}
                      onClick={() => setEditorState({ mode: "edit", record: item })}
                    >
                      <Pencil size={16} />
                    </IconButton>
                  )}
                  {isAdmin && (
                    <IconButton aria-label={`Delete ${item.title}`} onClick={() => setDeleteTarget(item)}>
                      <Trash2 size={16} />
                    </IconButton>
                  )}
                </div>
              </article>
            );
          })}
        </div>

        {/* Desktop Table */}
        <div className="hidden overflow-x-auto lg:block">
          <table className="w-full whitespace-nowrap text-left">
            <thead className="border-y border-slate-200 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-700">
              <tr>
                {["Event", "Schedule · IST", "Venue", "Assigned staff", "Status", "Actions"].map((heading) => (
                  <th key={heading} className="px-5 py-3">{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {visibleEvents.map((item) => {
                const canEdit = isAdmin && item.status !== "Completed" && item.status !== "Cancelled";
                const isAssigned = (item.assigned_user_ids || []).includes(user?.id);
                const myAttendance = attendanceMap[item.id];

                return (
                  <tr key={item.id} className="text-xs text-slate-800 transition-colors hover:bg-teal-50/40">
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        onClick={() => setSelectedEvent(item)}
                        className="flex items-center gap-3 text-left hover:text-teal-800"
                      >
                        <Avatar name={item.title} />
                        <span>
                          <strong className="block max-w-60 truncate font-semibold" title={item.title}>
                            {item.title}
                          </strong>
                          <small className="mt-1 block text-slate-600">{item.event_type}</small>
                        </span>
                      </button>
                    </td>
                    <td className="px-5 py-4">
                      <strong className="block font-medium text-slate-900">{formatDateTime(item.start_at)}</strong>
                      <small className="mt-1 block text-slate-600">to {formatDateTime(item.end_at)}</small>
                    </td>
                    <td className="px-5 py-4">
                      <span className="block max-w-44 truncate" title={item.venue || "—"}>
                        {item.venue || "—"}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="block max-w-48 truncate" title={renderAssignees(item)}>
                        {renderAssignees(item)}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <span
                        className={`rounded-md px-2 py-1 text-[10px] font-semibold ${
                          STATUS_BADGE[item.status] || "bg-slate-100 text-slate-800"
                        }`}
                      >
                        {item.status}
                      </span>
                      {myAttendance && (
                        <span className="ml-1.5 rounded-md bg-teal-100 px-2 py-0.5 text-[10px] font-semibold text-teal-900">
                          {myAttendance}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-1">
                        <IconButton
                          aria-label={`View ${item.title}`}
                          title="Event details"
                          onClick={() => setSelectedEvent(item)}
                        >
                          <Eye size={16} />
                        </IconButton>
                        {isAssigned && item.status !== "Cancelled" && (
                          <select
                            aria-label={`Attendance for ${item.title}`}
                            disabled={attendanceBusyId === item.id}
                            value={myAttendance || ""}
                            onChange={(event) => {
                              if (event.target.value) handleAttendance(item, event.target.value);
                            }}
                            className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-[11px] font-semibold text-slate-800 outline-none focus:border-teal-600"
                          >
                            <option value="" disabled>RSVP...</option>
                            {ATTENDANCE_OPTIONS.map((option) => (
                              <option key={option} value={option}>{option}</option>
                            ))}
                          </select>
                        )}
                        {canEdit && (
                          <IconButton
                            aria-label={`Edit ${item.title}`}
                            title="Edit event"
                            onClick={() => setEditorState({ mode: "edit", record: item })}
                          >
                            <Pencil size={16} />
                          </IconButton>
                        )}
                        {isAdmin && (
                          <IconButton
                            aria-label={`Delete ${item.title}`}
                            title="Delete event"
                            onClick={() => setDeleteTarget(item)}
                          >
                            <Trash2 size={16} />
                          </IconButton>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {!visibleEvents.length && !loading && (
          <EmptyState
            icon={CalendarDays}
            title={events.length ? "No matching events" : "No events scheduled yet"}
            description={
              events.length
                ? "Try clearing filters or choosing another date range."
                : isAdmin
                  ? "Schedule a workshop, meeting or team event using the button above."
                  : "Events assigned to you by an administrator will appear here."
            }
          />
        )}

        <footer className="border-t border-slate-200 px-5 py-4 text-xs text-slate-600">
          Showing {visibleEvents.length} of {events.length} event(s)
        </footer>
      </Card>

      {editorState && (
        <EventEditor
          record={editorState.record}
          staffUsers={staffUsers}
          staffError={staffError}
          onSave={handleSave}
          onClose={() => setEditorState(null)}
        />
      )}

      {selectedEvent && (
        <Modal title={selectedEvent.title} onClose={() => setSelectedEvent(null)}>
          <div className="space-y-4 p-5 text-xs leading-6 text-slate-800">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-teal-50 px-2.5 py-1 font-semibold text-teal-900">
                {selectedEvent.event_type}
              </span>
              <span
                className={`rounded-md px-2.5 py-1 font-semibold ${
                  STATUS_BADGE[selectedEvent.status] || "bg-slate-100 text-slate-800"
                }`}
              >
                {selectedEvent.status}
              </span>
            </div>

            <div className="grid gap-3 rounded-xl bg-slate-50 p-4 sm:grid-cols-2">
              <div>
                <span className="block text-[11px] font-semibold text-slate-500">Starts (IST)</span>
                <strong className="text-slate-950">{formatDateTime(selectedEvent.start_at)}</strong>
              </div>
              <div>
                <span className="block text-[11px] font-semibold text-slate-500">Ends (IST)</span>
                <strong className="text-slate-950">{formatDateTime(selectedEvent.end_at)}</strong>
              </div>
              <div className="sm:col-span-2">
                <span className="block text-[11px] font-semibold text-slate-500">Venue</span>
                <strong className="text-slate-950">{selectedEvent.venue || "Not specified"}</strong>
              </div>
            </div>

            <div>
              <span className="block text-[11px] font-semibold text-slate-500">Description</span>
              <p className="mt-1 whitespace-pre-wrap text-slate-800">
                {selectedEvent.description || "No description provided."}
              </p>
            </div>

            <div>
              <span className="block text-[11px] font-semibold text-slate-500">Reminders</span>
              <p className="mt-1 text-slate-800">
                {(selectedEvent.reminder_minutes || []).length
                  ? selectedEvent.reminder_minutes
                      .map((mins) => REMINDER_LABELS[mins] || `${mins} min`)
                      .join(" · ")
                  : "No reminders configured"}
              </p>
            </div>

            <div>
              <span className="block text-[11px] font-semibold text-slate-500">
                Assigned staff ({(selectedEvent.assigned_user_ids || []).length})
              </span>
              <p className="mt-1 text-slate-800">{renderAssignees(selectedEvent)}</p>
            </div>

            {(selectedEvent.assigned_user_ids || []).includes(user?.id) &&
              selectedEvent.status !== "Cancelled" && (
                <div className="rounded-xl border border-teal-200 bg-teal-50 p-4">
                  <strong className="block text-xs text-teal-950">Confirm your attendance</strong>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {ATTENDANCE_OPTIONS.map((option) => (
                      <Button
                        key={option}
                        variant={attendanceMap[selectedEvent.id] === option ? "primary" : "secondary"}
                        disabled={attendanceBusyId === selectedEvent.id}
                        onClick={() => handleAttendance(selectedEvent, option)}
                      >
                        {option}
                      </Button>
                    ))}
                  </div>
                </div>
              )}

            <div className="flex justify-end gap-2 border-t border-slate-200 pt-4">
              {isAdmin && selectedEvent.status !== "Completed" && selectedEvent.status !== "Cancelled" && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    const target = selectedEvent;
                    setSelectedEvent(null);
                    setEditorState({ mode: "edit", record: target });
                  }}
                >
                  <Pencil size={15} />
                  Edit event
                </Button>
              )}
              <Button onClick={() => setSelectedEvent(null)}>Close</Button>
            </div>
          </div>
        </Modal>
      )}

      {deleteTarget && (
        <Modal title="Delete event" onClose={deleting ? () => {} : () => setDeleteTarget(null)}>
          <div className="space-y-4 p-5 text-xs leading-6 text-slate-800">
            <p>
              Are you sure you want to delete <strong>{deleteTarget.title}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
              <Button variant="secondary" disabled={deleting} onClick={() => setDeleteTarget(null)}>
                Cancel
              </Button>
              <Button
                disabled={deleting}
                onClick={handleDelete}
                className="border-rose-700 bg-rose-700 hover:border-rose-900 hover:bg-rose-900"
              >
                <XCircle size={15} />
                {deleting ? "Deleting..." : "Delete event"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
