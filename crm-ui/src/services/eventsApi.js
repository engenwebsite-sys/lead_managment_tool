
import { apiRequest } from "./apiClient.js";

const BASE_URL = "/api/events";

// GET all events with optional filters
export function getEvents(filters = {}) {
    const params = new URLSearchParams();

    if (filters.start_date) {
        params.set("start_date", filters.start_date);
    }

    if (filters.end_date) {
        params.set("end_date", filters.end_date);
    }

    if (filters.status) {
        params.set("status", filters.status);
    }

    const query = params.toString();

    return apiRequest(`${BASE_URL}${query ? `?${query}` : ""}`);
}

// GET upcoming events
export function getUpcomingEvents(limit = 10) {
    return apiRequest(
        `${BASE_URL}/upcoming?limit=${encodeURIComponent(limit)}`
    );
}

// GET single event
export function getEventById(id) {
    return apiRequest(`${BASE_URL}/${encodeURIComponent(id)}`);
}

// CREATE event
export function createEvent(event) {
    return apiRequest(BASE_URL, {
        method: "POST",
        body: JSON.stringify(event),
    });
}

// UPDATE event
export function updateEvent(id, updates) {
    return apiRequest(`${BASE_URL}/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(updates),
    });
}

// UPDATE staff attendance
export function updateEventAttendance(id, attendanceStatus) {
    return apiRequest(
        `${BASE_URL}/${encodeURIComponent(id)}/attendance`,
        {
            method: "PATCH",
            body: JSON.stringify({
                attendance_status: attendanceStatus,
            }),
        }
    );
}

// DELETE event
export function deleteEvent(id) {
    return apiRequest(`${BASE_URL}/${encodeURIComponent(id)}`, {
        method: "DELETE",
    });
}
