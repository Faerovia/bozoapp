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

// ── Trainings (commit 11a+): šablona + přiřazení + pokusy ────────────────────

export type TrainingType = "bozp" | "po" | "other";
export type TrainerKind = "ozo_bozp" | "ozo_po" | "employer";
export type ValidityStatus = "no_expiry" | "valid" | "expiring_soon" | "expired";
export type AssignmentStatus = "pending" | "completed" | "expired" | "revoked";

export interface Training {
  id: string;
  tenant_id: string;
  title: string;
  training_type: TrainingType;
  trainer_kind: TrainerKind;
  valid_months: number;
  content_pdf_path: string | null;
  has_test: boolean;
  question_count: number;
  pass_percentage: number | null;
  notes: string | null;
  created_by: string;
  created_at: string;
}

export interface TrainingAssignment {
  id: string;
  tenant_id: string;
  training_id: string;
  training_title: string | null;
  training_type: string | null;
  employee_id: string;
  employee_name: string | null;
  assigned_at: string;
  deadline: string;
  last_completed_at: string | null;
  valid_until: string | null;
  validity_status: string;
  status: AssignmentStatus;
}

export interface TestQuestionForAttempt {
  question_index: number;
  question: string;
  options: string[];
}

export interface StartTestResponse {
  assignment_id: string;
  training_title: string;
  pass_percentage: number;
  questions: TestQuestionForAttempt[];
}

export interface SubmitTestResponse {
  attempt_id: string;
  score_percentage: number;
  passed: boolean;
  pass_percentage: number;
  assignment: TrainingAssignment;
}

export interface AssignmentCreateResponse {
  created_count: number;
  skipped_existing_count: number;
  errors: string[];
}

// ── Revisions (zařízení + timeline) ──────────────────────────────────────────

export type DueStatus = "no_schedule" | "ok" | "due_soon" | "overdue" | "upcoming";

export type DeviceType =
  | "elektro"
  | "hromosvody"
  | "plyn"
  | "kotle"
  | "tlakove_nadoby"
  | "vytahy"
  | "spalinove_cesty";

export const DEVICE_TYPE_LABELS: Record<DeviceType, string> = {
  elektro: "Elektrická zařízení",
  hromosvody: "Hromosvody",
  plyn: "Plynová zařízení",
  kotle: "Kotle",
  tlakove_nadoby: "Tlakové nádoby",
  vytahy: "Výtahy",
  spalinove_cesty: "Spalinové cesty",
};

export interface Revision {
  id: string;
  tenant_id: string;
  title: string;
  plant_id: string | null;
  plant_name: string | null;
  device_code: string | null;
  device_type: DeviceType | null;
  location: string | null;
  last_revised_at: string | null;
  valid_months: number | null;
  next_revision_at: string | null;
  due_status: DueStatus;
  technician_name: string | null;
  technician_email: string | null;
  technician_phone: string | null;
  contractor: string | null;
  responsible_user_id: string | null;
  qr_token: string;
  notes: string | null;
  status: "active" | "archived";
  created_by: string;
  revision_type: string;
}

export interface RevisionRecord {
  id: string;
  revision_id: string;
  performed_at: string;
  pdf_path: string | null;
  image_path: string | null;
  technician_name: string | null;
  notes: string | null;
  created_by: string;
}

export interface EmployeeResponsibilities {
  employee_id: string;
  plant_ids: string[];
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
