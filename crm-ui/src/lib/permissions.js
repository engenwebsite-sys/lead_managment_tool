import { divisions } from "../data/crm.js";

export function canAccessQuotations(user) {
  return user?.role === "Admin" || user?.canAccessQuotations === true;
}

export function leadAccessFor(user) {
  return user?.leadAccess ?? (user?.leadDivision ? { [user.leadDivision]: user.canCreateLeads === true } : {});
}
export function viewLeadDivisions(user) {
  const access = leadAccessFor(user);
  return user?.role === "Admin" ? divisions : divisions.filter((name) => Object.hasOwn(access, name));
}
