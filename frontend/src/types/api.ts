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

// ── Employees ─────────────────────────────────────────────────────────────────

export type EmploymentType = "hpp" | "dpp" | "dpc" | "externista" | "brigádník";
export type EmployeeStatus = "active" | "terminated" | "on_leave";

export interface Employee {
  id: string;
  tenant_id: string;
  user_id: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  personal_id: string | null;
  personal_number: string | null;
  birth_date: string | null;
  email: string | null;
  phone: string | null;
  address_street: string | null;
  address_city: string | null;
  address_zip: string | null;
  employment_type: EmploymentType;
  status: EmployeeStatus;
  hired_at: string | null;
  terminated_at: string | null;
  notes: string | null;
  plant_id: string | null;
  workplace_id: string | null;
  job_position_id: string | null;
  // Jen v response POST /employees pokud service vygeneroval heslo pro nový
  // auth účet. GET endpointy vracejí vždy null.
  generated_password?: string | null;
}

export interface EmployeeCreate {
  first_name: string;
  last_name: string;
  employment_type: EmploymentType;
  email?: string | null;
  phone?: string | null;
  birth_date?: string | null;
  personal_id?: string | null;
  personal_number?: string | null;
  address_street?: string | null;
  address_city?: string | null;
  address_zip?: string | null;
  hired_at?: string | null;
  notes?: string | null;
  plant_id?: string | null;
  workplace_id?: string | null;
  job_position_id?: string | null;
  user_id?: string | null;
  create_user_account?: boolean;
  user_password?: string | null;
  is_equipment_responsible?: boolean;
}

// ── Job Positions ──────────────────────────────────────────────────────────────

export interface JobPosition {
  id: string;
  name: string;
  description: string | null;
  work_category: string | null;
  medical_exam_period_months: number | null;
  effective_exam_period_months: number | null;
}

// ── Workplaces ─────────────────────────────────────────────────────────────────

export interface Plant {
  id: string;
  name: string;
  address: string | null;
  city: string | null;
}

export interface Workplace {
  id: string;
  plant_id: string;
  name: string;
  notes: string | null;
}

// ── Trainings ─────────────────────────────────────────────────────────────────

export type TrainingType =
  | "bozp_initial" | "bozp_periodic" | "fire_initial" | "fire_periodic"
  | "first_aid" | "driver" | "machinery" | "chemical" | "other";

export type ValidityStatus = "no_expiry" | "valid" | "expiring_soon" | "expired";

export interface Training {
  id: string;
  employee_id: string;
  employee_name: string | null;
  title: string;
  training_type: TrainingType;
  trained_at: string;
  valid_months: number | null;
  valid_until: string | null;
  validity_status: ValidityStatus;
  trainer_name: string | null;
  notes: string | null;
  status: "active" | "archived";
}

// ── Revisions ─────────────────────────────────────────────────────────────────

export type DueStatus = "upcoming" | "overdue" | "no_schedule";

export interface Revision {
  id: string;
  title: string;
  revision_type: string;
  description: string | null;
  last_revised_at: string | null;
  valid_months: number | null;
  next_revision_at: string | null;
  due_status: DueStatus;
  location: string | null;
  responsible_user_id: string | null;
  notes: string | null;
  status: "active" | "archived";
}

// ── Medical Exams ─────────────────────────────────────────────────────────────

export type ExamType = "vstupni" | "periodicka" | "vystupni" | "mimoradna";
export type ExamResult = "zpusobily" | "zpusobily_omezeni" | "nezpusobily" | "pozbyl_zpusobilosti";

export interface MedicalExam {
  id: string;
  employee_id: string;
  employee_name: string | null;
  exam_type: ExamType;
  exam_date: string;
  result: ExamResult | null;
  valid_months: number | null;
  valid_until: string | null;
  validity_status: ValidityStatus;
  days_until_expiry: number | null;
  doctor_name: string | null;
  notes: string | null;
}

// ── Accident Reports ──────────────────────────────────────────────────────────

export interface AccidentReport {
  id: string;
  title: string;
  accident_date: string;
  accident_time: string | null;
  location: string | null;
  description: string | null;
  employee_id: string | null;
  employee_name: string | null;
  injured_count: number;
  is_fatal: boolean;
  work_absence_days: number | null;
  risk_review_required: boolean;
  risk_review_completed_at: string | null;
  witnesses: { name: string; contact?: string }[];
  status: "draft" | "final" | "archived";
  created_at: string;
}

// ── OOPP ──────────────────────────────────────────────────────────────────────

export interface OOPPAssignment {
  id: string;
  employee_id: string | null;
  employee_name: string;
  oopp_type: string;
  oopp_name: string;
  issued_at: string;
  valid_until: string | null;
  validity_status: ValidityStatus;
  quantity: number;
  size_spec: string | null;
  serial_number: string | null;
  notes: string | null;
  status: "active" | "returned" | "discarded";
}

// ── Generický API error ───────────────────────────────────────────────────────

export interface ApiError {
  detail: string | { msg: string; loc: string[] }[];
}
