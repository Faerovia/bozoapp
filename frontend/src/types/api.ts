// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string | null;
  role: "ozo" | "manager" | "employee";
  is_active: boolean;
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export interface CalendarItem {
  id: string;
  title: string;
  due_date: string;       // ISO date
  source: "revision" | "training" | "medical_exam";
  is_overdue: boolean;
}

export interface DashboardResponse {
  pending_risk_reviews: number;
  expiring_trainings: number;
  overdue_revisions: number;
  draft_accident_reports: number;
  expiring_medical_exams: number;
  upcoming_calendar: CalendarItem[];
}

// ── Generický API error ───────────────────────────────────────────────────────

export interface ApiError {
  detail: string | { msg: string; loc: string[] }[];
}
