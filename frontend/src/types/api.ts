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
  role: "admin" | "ozo" | "hr_manager" | "equipment_responsible" | "employee" | "manager";
  is_active: boolean;
}

// ── OZO multi-tenant memberships ─────────────────────────────────────────────

export interface Membership {
  tenant_id: string;
  tenant_name: string;
  role: string;
  is_default: boolean;
}

export interface ClientMetrics {
  expiring_trainings: number;
  due_revisions: number;
  overdue_revisions: number;
  expiring_medical_exams: number;
  draft_accident_reports: number;
  expiring_oopp: number;
}

export interface ClientOverview {
  tenant_id: string;
  tenant_name: string;
  role: string;
  is_default: boolean;
  metrics: ClientMetrics;
  total_actions: number;
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export interface CalendarItem {
  source: "revision" | "risk" | "training" | "medical_exam";
  source_id: string;
  title: string;
  due_date: string;       // ISO date
  due_status: string;     // overdue | due_soon | ok
  responsible_user_id: string | null;
  detail_url: string;
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
  tenant_id: string;
  workplace_id: string;
  workplace_name: string | null;
  plant_id: string | null;
  plant_name: string | null;
  name: string;
  description: string | null;
  work_category: string | null;
  effective_category: string | null;    // derived z RFA nebo override
  medical_exam_period_months: number | null;
  effective_exam_period_months: number | null;
  notes: string | null;
  status: "active" | "archived";
  created_by: string;
}

// ── Workplaces ─────────────────────────────────────────────────────────────────

export interface Plant {
  id: string;
  name: string;
  address: string | null;
  city: string | null;
  zip_code: string | null;
  ico: string | null;
  plant_number: string | null;
  notes: string | null;
  status: "active" | "archived";
}

export interface Workplace {
  id: string;
  plant_id: string;
  name: string;
  notes: string | null;
  status: "active" | "archived";
}

// ── Risk Factor Assessment (hodnocení rizik per pozice) ──────────────────────

export type RiskFactor =
  | "rf_prach"
  | "rf_chem"
  | "rf_hluk"
  | "rf_vibrace"
  | "rf_zareni"
  | "rf_tlak"
  | "rf_fyz_zatez"
  | "rf_prac_poloha"
  | "rf_teplo"
  | "rf_chlad"
  | "rf_psych"
  | "rf_zrak"
  | "rf_bio";

export const RF_LABELS: Record<RiskFactor, string> = {
  rf_hluk: "Hluk",
  rf_prach: "Prach",
  rf_vibrace: "Vibrace",
  rf_teplo: "Zátěž teplem",
  rf_chlad: "Zátěž chladem",
  rf_tlak: "Práce ve zvýšeném tlaku vzduchu",
  rf_zareni: "Neionizující záření a EM pole",
  rf_chem: "Chemické látky",
  rf_bio: "Biologické činitele",
  rf_prac_poloha: "Pracovní poloha",
  rf_fyz_zatez: "Fyzická zátěž",
  rf_psych: "Psychická zátěž",
  rf_zrak: "Zraková zátěž",
};

export const RF_ORDER: RiskFactor[] = [
  "rf_hluk",
  "rf_prach",
  "rf_vibrace",
  "rf_teplo",
  "rf_chlad",
  "rf_tlak",
  "rf_zareni",
  "rf_chem",
  "rf_bio",
  "rf_prac_poloha",
  "rf_fyz_zatez",
  "rf_psych",
  "rf_zrak",
];

export type RiskRating = "1" | "2" | "2R" | "3" | "4";
export const RISK_RATINGS: RiskRating[] = ["1", "2", "2R", "3", "4"];

export interface RiskFactorAssessment {
  id: string;
  tenant_id: string;
  workplace_id: string | null;
  job_position_id: string;
  profese: string;
  operator_names: string | null;
  worker_count: number;
  women_count: number;

  rf_prach:       RiskRating | null;
  rf_chem:        RiskRating | null;
  rf_hluk:        RiskRating | null;
  rf_vibrace:     RiskRating | null;
  rf_zareni:      RiskRating | null;
  rf_tlak:        RiskRating | null;
  rf_fyz_zatez:   RiskRating | null;
  rf_prac_poloha: RiskRating | null;
  rf_teplo:       RiskRating | null;
  rf_chlad:       RiskRating | null;
  rf_psych:       RiskRating | null;
  rf_zrak:        RiskRating | null;
  rf_bio:         RiskRating | null;

  rf_prach_pdf_path:       string | null;
  rf_chem_pdf_path:        string | null;
  rf_hluk_pdf_path:        string | null;
  rf_vibrace_pdf_path:     string | null;
  rf_zareni_pdf_path:      string | null;
  rf_tlak_pdf_path:        string | null;
  rf_fyz_zatez_pdf_path:   string | null;
  rf_prac_poloha_pdf_path: string | null;
  rf_teplo_pdf_path:       string | null;
  rf_chlad_pdf_path:       string | null;
  rf_psych_pdf_path:       string | null;
  rf_zrak_pdf_path:        string | null;
  rf_bio_pdf_path:         string | null;

  category_proposed: string;
  category_override: string | null;
  sort_order: number;
  notes: string | null;
  status: "active" | "archived";
  created_by: string;
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
  vytahy: "Zdvihací zařízení",
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

export type AccidentTestResult = "negative" | "positive";

export interface AccidentWitness {
  name: string;
  signed_at: string | null;
}

export interface AccidentReport {
  id: string;
  tenant_id: string;

  employee_id: string | null;
  employee_name: string;
  workplace: string;

  accident_date: string;
  accident_time: string;
  shift_start_time: string | null;

  injury_type: string;
  injured_body_part: string;
  injury_source: string;
  injury_cause: string;
  injured_count: number;
  is_fatal: boolean;
  has_other_injuries: boolean;

  description: string;

  blood_pathogen_exposure: boolean;
  blood_pathogen_persons: string | null;

  violated_regulations: string | null;

  alcohol_test_performed: boolean;
  alcohol_test_result: AccidentTestResult | null;
  alcohol_test_value: string | number | null;  // promile (Decimal serializovaný jako string)
  drug_test_performed: boolean;
  drug_test_result: AccidentTestResult | null;

  injured_signed_at: string | null;
  witnesses: AccidentWitness[];
  supervisor_name: string | null;
  supervisor_signed_at: string | null;

  risk_id: string | null;
  risk_review_required: boolean;
  risk_review_completed_at: string | null;

  status: "draft" | "final" | "archived";
  signed_document_path: string | null;
  created_by: string;
}

// ── OOPP (NV 390/2021 Sb. — Příloha č. 2) ────────────────────────────────────

export interface OoppCatalogBodyPart {
  key: string;          // A-N
  label: string;
  group: string | null; // např. "hlava"
}

export interface OoppCatalogRiskColumn {
  col: number;          // 1-26
  label: string;
  subgroup: string | null;
  group: string;        // fyzikální / chemická / biologické / jiná
}

export interface OoppCatalog {
  body_parts: OoppCatalogBodyPart[];
  risk_columns: OoppCatalogRiskColumn[];
}

export interface RiskGrid {
  id: string;
  tenant_id: string;
  job_position_id: string;
  grid: Record<string, number[]>; // { "G": [1, 6], ... }
  has_any_risk: boolean;
  created_by: string;
}

export interface OoppItem {
  id: string;
  tenant_id: string;
  job_position_id: string;
  body_part: string;     // A-N
  name: string;
  valid_months: number | null;
  notes: string | null;
  status: "active" | "archived";
  created_by: string;
}

export interface OoppIssue {
  id: string;
  tenant_id: string;
  employee_id: string;
  employee_name: string | null;
  position_oopp_item_id: string;
  item_name: string | null;
  body_part: string | null;
  issued_at: string;
  valid_until: string | null;
  validity_status: ValidityStatus;
  quantity: number;
  size_spec: string | null;
  serial_number: string | null;
  notes: string | null;
  status: "active" | "returned" | "discarded";
  created_by: string;
}

// ── Documents (generátor BOZP/PO) ────────────────────────────────────────────

export type DocumentType =
  | "bozp_directive"
  | "training_outline"
  | "revision_schedule"
  | "risk_categorization";

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  bozp_directive: "Směrnice BOZP",
  training_outline: "Osnova školení BOZP (per pozice)",
  revision_schedule: "Harmonogram revizí",
  risk_categorization: "Kategorizace prací (RFA)",
};

export const DOCUMENT_TYPE_DESC: Record<DocumentType, string> = {
  bozp_directive:
    "Kompletní směrnice BOZP firmy generovaná AI z dat tenantu (cca 10 stran).",
  training_outline:
    "Osnova vstupního školení BOZP pro konkrétní pracovní pozici. Generuje AI z RFA.",
  revision_schedule:
    "Tabulkový přehled všech revizí s termíny. Bez AI — čistá data.",
  risk_categorization:
    "Tabulka kategorií prací dle NV 361/2007. Z RFA, bez AI.",
};

export interface GeneratedDocumentListItem {
  id: string;
  document_type: DocumentType;
  title: string;
  ai_input_tokens: number | null;
  ai_output_tokens: number | null;
  created_by: string;
}

export interface GeneratedDocument {
  id: string;
  tenant_id: string;
  document_type: DocumentType;
  title: string;
  content_md: string;
  params: Record<string, unknown>;
  ai_input_tokens: number | null;
  ai_output_tokens: number | null;
  created_by: string;
}

// ── Generický API error ───────────────────────────────────────────────────────

export interface ApiError {
  detail: string | { msg: string; loc: string[] }[];
}
