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
  username: string | null;
  full_name: string | null;
  role: "admin" | "ozo" | "hr_manager" | "lead_worker" | "equipment_responsible" | "employee" | "manager";
  is_active: boolean;
  is_platform_admin: boolean;
}

// ── OZO multi-tenant memberships ─────────────────────────────────────────────

export interface Membership {
  tenant_id: string;
  tenant_slug: string;
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
  workplaces_without_category?: number;
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
  gender: "M" | "F" | "X" | null;
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
  // Opt-out vstupní prohlídky (jen pro cat 1). Default false = vyžaduje se.
  skip_vstupni_exam: boolean;
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

export type TrainingStatus = "active" | "pending_approval" | "archived";

export interface Training {
  id: string;
  tenant_id: string | null;
  title: string;
  training_type: TrainingType;
  trainer_kind: TrainerKind;
  valid_months: number;
  content_pdf_path: string | null;
  has_test: boolean;
  question_count: number;
  pass_percentage: number | null;
  notes: string | null;
  outline_text: string | null;
  duration_hours: number | null;
  requires_qes: boolean;
  knowledge_test_required: boolean;
  created_by: string;
  created_at: string;
  // Approval workflow + autor/OZO podpis obsahu (#105)
  status: TrainingStatus;
  requires_ozo_approval: boolean;
  author_signature_id: string | null;
  ozo_approval_signature_id: string | null;
  approved_at: string | null;
  approved_by_user_id: string | null;
}

export interface TrainingAssignment {
  id: string;
  tenant_id: string;
  training_id: string;
  training_title: string | null;
  training_type: string | null;
  training_requires_qes?: boolean;
  employee_id: string;
  employee_name: string | null;
  assigned_at: string;
  deadline: string;
  last_completed_at: string | null;
  valid_until: string | null;
  validity_status: string;
  status: AssignmentStatus;
  signed_at?: string | null;
  signature_method?: "simple" | "qes" | null;
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
  | "spalinove_cesty"
  | "regaly";

export const DEVICE_TYPE_LABELS: Record<DeviceType, string> = {
  elektro: "Elektrická zařízení",
  hromosvody: "Hromosvody",
  plyn: "Plynová zařízení",
  kotle: "Kotle",
  tlakove_nadoby: "Tlakové nádoby",
  vytahy: "Zdvihací zařízení",
  spalinove_cesty: "Spalinové cesty",
  regaly: "Regálové systémy",
};

/**
 * Legislativní požadavky pro periodicitu revizí per device_type.
 * Zobrazuje se v info-tooltipu vedle pole "Periodicita".
 */
export const DEVICE_TYPE_PERIODICITY_INFO: Record<DeviceType, string> = {
  elektro:
    "Vyhl. 73/2010 Sb. + ČSN 33 1500: lhůty dle prostředí — běžné prostory 5 let, " +
    "vlhké/horké/prašné 3 roky, mokré/výbušné 1–2 roky. Drobné spotřebiče dle ČSN 33 1600 " +
    "(6 měs. – 2 roky).",
  hromosvody:
    "ČSN EN 62305-3: hladina ochrany I/II — 2 roky, hladina III/IV — 4 roky. " +
    "Po každém přímém úderu blesku mimořádná revize.",
  plyn:
    "Vyhl. 85/1978 Sb.: provozní revize 1× ročně, kontrola 1× za 3 roky. " +
    "Domácí plynové spotřebiče: kontrola dle TPG 704 01 (1–3 roky).",
  kotle:
    "Zákon 406/2000 Sb. + vyhl. 194/2013 Sb.: kontrola účinnosti 2–10 let dle výkonu " +
    "(plyn 4–10 let, pevná paliva 2–5 let). Kotle nad 100 kW evidované.",
  tlakove_nadoby:
    "ČSN 69 0012 + NV 192/2022 Sb.: provozní revize ročně, vnitřní revize 5 let, " +
    "tlaková zkouška 9 let. Pojistné ventily ročně.",
  vytahy:
    "ČSN 27 4002 / 27 4007: provozní prohlídka 14 dní – 3 měs., odborná prohlídka 3–6 měs., " +
    "odborná zkouška 3 roky, inspekční prohlídka 6 let. Jeřáby NV 378/2001 ročně.",
  spalinove_cesty:
    "Vyhl. 34/2016 Sb. + NV 91/2010 Sb.: čištění komínů 1–3× ročně dle paliva, " +
    "kontrola 1× ročně, revize při změně paliva / po požáru.",
  regaly:
    "ČSN EN 15635: vizuální inspekce min. 1× ročně osobou pověřenou (PRRS — " +
    "Person Responsible for Rack Safety). Provozní kontroly týdně/měsíčně. " +
    "Po každém poškození mimořádná inspekce.",
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
  auto_request_enabled: boolean;
  auto_request_sent_at: string | null;
  created_by: string;
  revision_type: string;
}

// ── Periodic checks (sanační sady, záchytné vany, lékárničky) ──────────────

export type CheckKind = "sanitation_kit" | "spill_tray" | "first_aid_kit";

export const CHECK_KIND_LABELS: Record<CheckKind, string> = {
  sanitation_kit: "Sanační sada",
  spill_tray:     "Záchytná vana",
  first_aid_kit:  "Lékárnička",
};

export const CHECK_KIND_PERIODICITY_INFO: Record<CheckKind, string> = {
  sanitation_kit:
    "Vyhl. 432/2003 Sb. + NV 11/2002 Sb.: kontrola obsahu sanační sady min. 1× ročně, " +
    "po každém použití okamžitá kontrola a doplnění.",
  spill_tray:
    "NV 11/2002 Sb. + ČSN EN 13160: vizuální kontrola integrity záchytných van min. " +
    "1× měsíčně. Kontrola těsnosti 1× ročně.",
  first_aid_kit:
    "Vyhl. 296/2022 Sb. + § 102 odst. 6 ZP: kontrola obsahu a expirace léčiv min. " +
    "1× ročně. Po každém použití okamžitá kontrola a doplnění chybějících položek.",
};

export interface PeriodicCheck {
  id: string;
  tenant_id: string;
  check_kind: CheckKind;
  title: string;
  location: string | null;
  plant_id: string | null;
  plant_name: string | null;
  workplace_id: string | null;
  last_checked_at: string | null;
  valid_months: number | null;
  next_check_at: string | null;
  due_status: DueStatus;
  responsible_user_id: string | null;
  responsible_employee_id: string | null;
  responsible_employee_name: string | null;
  notes: string | null;
  status: "active" | "archived";
  created_by: string;
}

export interface PeriodicCheckRecord {
  id: string;
  periodic_check_id: string;
  performed_at: string;
  performed_by_name: string | null;
  result: "ok" | "fixed" | "issue";
  notes: string | null;
  file_path: string | null;
  created_by: string;
}

// ── Operating logs (provozní deníky) ────────────────────────────────────────

export type DeviceCategory =
  | "vzv" | "kotelna" | "tlakova_nadoba" | "jerab" | "eps" | "sprinklery"
  | "cov" | "diesel" | "regaly_sklad" | "vytah" | "stroje_riziko" | "other";

export const DEVICE_CATEGORY_LABELS: Record<DeviceCategory, string> = {
  vzv: "Vysokozdvižné vozíky (VZV)",
  kotelna: "Kotelny (nad 100 kW)",
  tlakova_nadoba: "Tlakové nádoby (TNS)",
  jerab: "Jeřáby a zdvihadla",
  eps: "Elektrická požární signalizace (EPS)",
  sprinklery: "Stabilní hasicí zařízení (sprinklery)",
  cov: "Čističky odpadních vod / Odlučovače",
  diesel: "Náhradní zdroje (Dieselagregáty)",
  regaly_sklad: "Regálové systémy (sklady)",
  vytah: "Výtahy (osobní/nákladní)",
  stroje_riziko: "Stroje s vyšším rizikem (lisy, pily)",
  other: "Jiné",
};

/**
 * Doporučená periodicita zápisů do provozního deníku per kategorie
 * (zdroj: Příloha s legislativními požadavky a typickými intervaly).
 */
export const DEVICE_CATEGORY_PERIODICITY_INFO: Record<DeviceCategory, string> = {
  vzv: "Denně před začátkem směny (NV 168/2002 + ČSN 26 8805): brzdy, řízení, hydraulika, pneumatiky.",
  kotelna: "Denně dle typu obsluhy (vyhl. 91/1993 Sb.): tlak, teplota, těsnost, regulace, údaje do PD.",
  tlakova_nadoba: "Denně/týdně (NV 192/2022 + ČSN 69 0012): tlak, odkalování, pojistné ventily.",
  jerab: "Denně před zahájením (NV 378/2001 + ČSN ISO 9927): lana/řetězy, háky, ovladače, koncové vypínače.",
  eps: "Denně + měsíčně (vyhl. 246/2001): denně ústředna, měsíčně testy hlásičů a sirén.",
  sprinklery: "Týdně (ČSN EN 12845): tlak v soustavě, čerpadla, hladiny zásob vody.",
  cov: "Týdně/měsíčně: stav kalu, dmychadla, záznamy spotřeby, údržbové úkony.",
  diesel: "Měsíčně (ČSN ISO 8528): zkušební start naprázdno/v zátěži, palivo, baterie.",
  regaly_sklad: "Týdně/měsíčně (ČSN EN 15635): vizuální kontrola stojin/nosníků, poškození, deformace.",
  vytah: "Dle návodu, obvykle týdně (ČSN 27 4002): provozní prohlídka dozorcem výtahu, osvětlení, alarm.",
  stroje_riziko: "Denně před směnou (NV 378/2001): ochranné kryty, nouzové vypínače, signalizace, čistota.",
  other: "Periodicitu definuj podle výrobce / dle typu zařízení.",
};

export type OperatingPeriod = "daily" | "weekly" | "monthly" | "shift" | "other";
export const OPERATING_PERIOD_LABELS: Record<OperatingPeriod, string> = {
  daily: "Denně",
  weekly: "Týdně",
  monthly: "Měsíčně",
  shift: "Před každou směnou",
  other: "Jiné",
};

export interface OperatingLogDevice {
  id: string;
  tenant_id: string;
  category: DeviceCategory;
  title: string;
  device_code: string | null;
  location: string | null;
  plant_id: string | null;
  plant_name: string | null;
  workplace_id: string | null;
  check_items: string[];
  period: OperatingPeriod;
  period_note: string | null;
  qr_token: string;
  notes: string | null;
  status: "active" | "archived";
  created_by: string;
  responsible_employee_id: string | null;
  responsible_employee_name: string | null;
}

export type CapabilityStatus = "yes" | "no" | "conditional";

export const CAPABILITY_STATUS_LABELS: Record<CapabilityStatus, string> = {
  yes: "ANO",
  no: "NE",
  conditional: "Podmíněný",
};

export interface OperatingLogEntry {
  id: string;
  device_id: string;
  performed_at: string;
  performed_by_name: string;
  capable_items: CapabilityStatus[];
  overall_status: CapabilityStatus;
  notes: string | null;
  created_by: string;
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

export type ExamType = "vstupni" | "periodicka" | "vystupni" | "mimoradna" | "odborna";
export type ExamResult = "zpusobily" | "zpusobily_omezeni" | "nezpusobily" | "pozbyl_zpusobilosti";

export type ExamCategory = "preventivni" | "odborna";

export type SpecialtyKey =
  | "audiometrie"
  | "spirometrie"
  | "prstova_plethysmografie"
  | "ekg_klidove"
  | "ocni_vysetreni"
  | "rtg_plic"
  | "psychotesty";

export interface SpecialtyCatalogEntry {
  key: SpecialtyKey | string;
  label: string;
  purpose: string;
  examples: string;
}

export interface MedicalExam {
  id: string;
  tenant_id: string;
  employee_id: string;
  employee_name: string | null;
  employee_personal_id: string | null;
  employee_personal_number: string | null;
  job_position_id: string | null;
  job_position_name: string | null;
  work_category: string | null;
  exam_category: ExamCategory;
  exam_type: ExamType;
  specialty: string | null;
  specialty_label: string | null;
  exam_date: string;
  result: ExamResult | null;
  valid_months: number | null;
  valid_until: string | null;
  validity_status: ValidityStatus;
  days_until_expiry: number | null;
  has_report: boolean;
  physician_name: string | null;
  notes: string | null;
  status: "active" | "archived";
}

// ── Accident Reports ──────────────────────────────────────────────────────────

export type AccidentTestResult = "negative" | "positive";

export interface AccidentWitness {
  name: string;
  /** Pokud null, svědek je externí (digi podpis nelze). */
  employee_id: string | null;
  signed_at: string | null;
}

export interface AccidentReport {
  id: string;
  tenant_id: string;

  employee_id: string | null;
  employee_name: string;
  workplace: string;
  workplace_id: string | null;
  workplace_external_description: string | null;

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
  injured_external: boolean;
  witnesses: AccidentWitness[];
  supervisor_name: string | null;
  supervisor_employee_id: string | null;
  supervisor_signed_at: string | null;

  risk_id: string | null;
  risk_review_required: boolean;
  risk_review_completed_at: string | null;

  status: "draft" | "final" | "archived";
  signed_document_path: string | null;
  created_by: string;

  // Univerzální digitální podpis (#105)
  signature_required: boolean;
  required_signer_employee_ids: string[];
  signed_count: number;
  is_fully_signed: boolean;
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
  signature_id: string | null;
  is_signed: boolean;
}

// ── Univerzální digitální podpis (migrace 057) ──────────────────────────────

export type SignatureDocType =
  | "oopp_issue"
  | "accident_report"
  | "training_attempt"
  | "training_content";
export type SignatureAuthMethod = "password" | "sms_otp";

export interface SignatureRecord {
  id: string;
  doc_type: SignatureDocType;
  doc_id: string;
  employee_id: string;
  employee_full_name_snapshot: string;
  auth_method: SignatureAuthMethod;
  payload_hash: string;
  seq: number;
  chain_hash: string;
  signed_at: string;
}

export interface SignatureInitiateResponse {
  ok: boolean;
  auth_method: SignatureAuthMethod;
  sms_sent_to: string | null;
  expires_in_seconds: number | null;
  message: string;
}

// ── Tenant-level role (assignovatelné OZO/HR při tvorbě zaměstnance) ─────────

export type AssignableRole =
  | "ozo"
  | "hr_manager"
  | "lead_worker"
  | "equipment_responsible"
  | "employee";

export const ASSIGNABLE_ROLE_LABELS: Record<AssignableRole, string> = {
  ozo: "OZO BOZP/PO",
  hr_manager: "HR manager",
  lead_worker: "Vedoucí pracovník",
  equipment_responsible: "Zaměstnanec — zodpovědný za vyhrazená zařízení",
  employee: "Zaměstnanec",
};


// ── Documents (generátor BOZP/PO) ────────────────────────────────────────────

export type DocumentType =
  | "bozp_directive"
  | "training_outline"
  | "revision_schedule"
  | "risk_categorization"
  | "operating_log_summary"
  | "imported";

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  bozp_directive: "Směrnice BOZP",
  training_outline: "Osnova školení BOZP (per pozice)",
  revision_schedule: "Harmonogram revizí",
  risk_categorization: "Kategorizace prací (RFA)",
  operating_log_summary: "Provozní deníky — souhrn",
  imported: "Importováno",
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
  operating_log_summary:
    "Souhrn provozních deníků zařízení — kategorie, kontrolní úkony, "
    + "posledních 5 zápisů per zařízení. Pro audit SÚIP / OIP.",
  imported:
    "Externě nahraný textový dokument (PDF/DOCX/MD/TXT).",
};

export interface GeneratedDocumentListItem {
  id: string;
  folder_id: string | null;
  document_type: DocumentType;
  title: string;
  ai_input_tokens: number | null;
  ai_output_tokens: number | null;
  created_by: string;
}

export interface GeneratedDocument {
  id: string;
  tenant_id: string;
  folder_id: string | null;
  document_type: DocumentType;
  title: string;
  content_md: string;
  params: Record<string, unknown>;
  ai_input_tokens: number | null;
  ai_output_tokens: number | null;
  created_by: string;
}

// ── Invoices (Fakturace) ──────────────────────────────────────────────────────

export type InvoiceStatus = "draft" | "sent" | "paid" | "cancelled";

export interface InvoiceItem {
  description: string;
  quantity: number;
  unit: string;
  unit_price: number;
  total: number;
}

export interface InvoiceListItem {
  id: string;
  tenant_id: string;
  invoice_number: string;
  issued_at: string;
  due_date: string;
  period_from: string;
  period_to: string;
  paid_at: string | null;
  status: InvoiceStatus;
  currency: string;
  total: string; // Decimal as string (Pydantic 2)
}

export interface Invoice extends InvoiceListItem {
  sent_at: string | null;
  subtotal: string;
  vat_rate: string;
  vat_amount: string;
  issuer_snapshot: Record<string, unknown>;
  recipient_snapshot: Record<string, unknown>;
  items: InvoiceItem[];
  notes: string | null;
  pdf_path: string | null;
  created_at: string;
  updated_at: string;
}

export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: "Koncept",
  sent: "Odeslána",
  paid: "Zaplaceno",
  cancelled: "Storno",
};

// ── Generický API error ───────────────────────────────────────────────────────

export interface ApiError {
  detail: string | { msg: string; loc: string[] }[];
}
