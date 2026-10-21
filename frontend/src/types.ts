export interface PriorityWeightsConfig {
  overdue_max_points: number;
  overdue_points_per_day: number;
  pre_due_window_days: number;
  pre_due_points: number;
  amount_max_points: number;
  amount_reference_cap_inr: number;
  followup_max_points: number;
  unfollowed_overdue_points: number;
  unanswered_reminder_points: number;
  partial_payment_reconcile_points: number;
}

export interface PriorityBreakdown {
  overdue_points: number;
  amount_points: number;
  followup_points: number;
  total_score: number;
  scoring_method: string;
  explanation_summary: string;
  factors: string[];
}

export interface Customer {
  id: number;
  name: string;
  company_name: string;
  gstin: string;
  udyam_number?: string;
  email: string;
  phone: string;
  city: string;
  credit_period_days: number;
  reliability_score: number;
  total_invoiced: number;
  total_paid: number;
  total_outstanding: number;
  overdue_amount: number;
  overdue_invoices_count: number;
  invoices_count: number;
  paid_invoices_count: number;
  risk_badge: string;
  historical_data_note: string;
}

export interface Invoice {
  id: number;
  invoice_number: string;
  customer_id: number;
  customer_name: string;
  company_name: string;
  customer_gstin: string;
  customer_udyam?: string;
  customer_phone: string;
  customer_email: string;
  issue_date: string;
  due_date: string;
  total_amount: number;
  amount_paid: number;
  balance_due: number;
  description: string;
  msme_agreement: boolean;
  status: 'Paid' | 'Partially Paid' | 'Pending' | 'Overdue';
  days_overdue: number;
  days_until_due: number;
  days_since_issue: number;
  statutory_limit_days: number;
  aging_bucket: string;
  msmed_interest: number;
  total_claimable: number;
  section_43bh_at_risk: boolean;
  risk_level: 'Low' | 'Medium' | 'High' | 'Critical';
  priority_score: number;
  priority_breakdown: PriorityBreakdown;
  priority_explanation: string;
  ai_recommended_action: string;
  next_action_type: string;
  reminders_logged_count: number;
  payments_recorded_count: number;
}

export interface Payment {
  id: number;
  invoice_id: number;
  invoice_number: string;
  company_name: string;
  amount: number;
  payment_date: string;
  payment_mode: string;
  reference_number?: string;
  notes?: string;
}

export interface AgingBucket {
  bucket: string;
  amount: number;
  count: number;
}

export interface NextActionItem {
  invoice_id: number;
  invoice_number: string;
  company_name: string;
  action_type: string;
  action_label: string;
  priority_level: string;
  priority_score: number;
  balance_due: number;
  msmed_interest: number;
  days_overdue: number;
  days_until_due: number;
  visible_reason: string;
  recommended_tone: string;
  recommended_channel: string;
}

export interface CashFlowScenarioBand {
  name: string;
  expected_inflow_30d: number;
  expected_principal_inflow_30d: number;
  expected_interest_inflow_30d: number;
  collection_share_of_outstanding_pct: number;
  assumptions_summary: string;
  bucket_breakdown: Record<string, number>;
}

export interface CashFlowScenariosReport {
  horizon_days: number;
  total_current_outstanding: number;
  total_accrued_interest: number;
  conservative: CashFlowScenarioBand;
  baseline: CashFlowScenarioBand;
  optimistic: CashFlowScenarioBand;
  historical_settled_invoices_count: number;
  insufficient_historical_data: boolean;
  methodology_disclaimer: string;
}

export interface DashboardSummary {
  kpis: {
    total_invoiced: number;
    total_collected: number;
    total_outstanding: number;
    total_overdue: number;
    total_current_not_due: number;
    total_msmed_interest: number;
    total_claimable_with_interest: number;
    collection_rate: number;
    open_invoices_count: number;
    overdue_invoices_count: number;
    current_not_due_count: number;
    section_43bh_count: number;
    rbi_bank_rate_percent: number;
    msmed_statutory_rate_percent: number;
    statutory_assumptions_note: string;
  };
  aging_breakdown: AgingBucket[];
  priority_queue: Invoice[];
  next_action_queue: NextActionItem[];
  cashflow_scenarios: CashFlowScenariosReport;
  priority_weights: PriorityWeightsConfig;
}

export interface ReminderDraft {
  invoice_id: number;
  invoice_number: string;
  company_name: string;
  contact_name: string;
  channel: string;
  tone: string;
  subject: string;
  message_body: string;
  balance_due: number;
  msmed_interest: number;
  total_claimable: number;
  days_overdue: number;
  ai_rationale: string;
  delivery_status: string;
}

export interface ReminderLog {
  id: number;
  invoice_id: number;
  invoice_number: string;
  company_name: string;
  channel: string;
  tone: string;
  subject: string;
  message_body: string;
  snapshot_balance_due?: number;
  snapshot_interest?: number;
  snapshot_total_claimable?: number;
  delivery_status: string;
  created_at: string;
}

export interface TimelineEvent {
  id: number;
  invoice_id: number;
  invoice_number: string;
  event_type: string;
  title: string;
  details: string;
  amount?: number;
  balance_after?: number;
  interest_snapshot?: number;
  delivery_status?: string;
  created_at: string;
}

export interface EvidenceChecklistItem {
  item_key: string;
  label: string;
  status: string;
  details: string;
}

export interface InvoiceWorkspace {
  invoice: Invoice;
  payments: Payment[];
  reminders: ReminderLog[];
  timeline: TimelineEvent[];
  evidence_checklist: EvidenceChecklistItem[];
  reconciliation_verified: boolean;
  legal_disclaimer: string;
}
