from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List, Dict, Any


class PriorityWeightsConfig(BaseModel):
    overdue_max_points: int = Field(default=50, ge=10, le=80)
    overdue_points_per_day: float = Field(default=1.0, ge=0.1, le=5.0)
    pre_due_window_days: int = Field(default=7, ge=1, le=15)
    pre_due_points: int = Field(default=12, ge=0, le=30)
    amount_max_points: int = Field(default=30, ge=10, le=60)
    amount_reference_cap_inr: float = Field(default=400000.0, ge=10000.0, le=10000000.0)
    followup_max_points: int = Field(default=20, ge=5, le=40)
    unfollowed_overdue_points: int = Field(default=20, ge=0, le=40)
    unanswered_reminder_points: int = Field(default=14, ge=0, le=40)
    partial_payment_reconcile_points: int = Field(default=10, ge=0, le=30)


class CustomerCreate(BaseModel):
    name: str
    company_name: str
    gstin: str
    udyam_number: Optional[str] = None
    email: str
    phone: str
    city: str
    credit_period_days: int = Field(default=30, ge=1, le=90)


class CustomerRead(BaseModel):
    id: int
    name: str
    company_name: str
    gstin: str
    udyam_number: Optional[str] = None
    email: str
    phone: str
    city: str
    credit_period_days: int
    reliability_score: int
    total_invoiced: float
    total_paid: float
    total_outstanding: float
    overdue_amount: float
    overdue_invoices_count: int
    invoices_count: int
    paid_invoices_count: int
    risk_badge: str
    historical_data_note: str

    class Config:
        from_attributes = True


class InvoiceCreate(BaseModel):
    invoice_number: str
    customer_id: int
    issue_date: date
    due_date: date
    total_amount: float = Field(gt=0)
    description: str
    msme_agreement: bool = True


class PriorityBreakdown(BaseModel):
    overdue_points: int
    amount_points: int
    followup_points: int
    total_score: int
    scoring_method: str
    explanation_summary: str
    factors: List[str]


class InvoiceComputed(BaseModel):
    id: int
    invoice_number: str
    customer_id: int
    customer_name: str
    company_name: str
    customer_gstin: str
    customer_udyam: Optional[str] = None
    customer_phone: str
    customer_email: str
    issue_date: date
    due_date: date
    total_amount: float
    amount_paid: float
    balance_due: float
    description: str
    msme_agreement: bool
    status: str  # Paid, Partially Paid, Pending, Overdue
    days_overdue: int
    days_until_due: int
    days_since_issue: int
    statutory_limit_days: int
    aging_bucket: str
    msmed_interest: float
    total_claimable: float
    section_43bh_at_risk: bool
    risk_level: str  # Low, Medium, High, Critical
    priority_score: int
    priority_breakdown: PriorityBreakdown
    priority_explanation: str
    ai_recommended_action: str
    next_action_type: str
    reminders_logged_count: int
    payments_recorded_count: int


class PaymentCreate(BaseModel):
    invoice_id: int
    amount: float = Field(gt=0)
    payment_date: date
    payment_mode: str = "NEFT"
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class PaymentRead(BaseModel):
    id: int
    invoice_id: int
    invoice_number: str
    company_name: str
    amount: float
    payment_date: date
    payment_mode: str
    reference_number: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class ReminderDraftRequest(BaseModel):
    invoice_id: int
    tone: str = "Polite"  # Polite, Firm, Statutory MSME
    channel: str = "WhatsApp"  # WhatsApp, Email, Demand Notice
    log_draft_event: bool = False


class ReminderDraftResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    company_name: str
    contact_name: str
    channel: str
    tone: str
    subject: str
    message_body: str
    balance_due: float
    msmed_interest: float
    total_claimable: float
    days_overdue: int
    ai_rationale: str
    delivery_status: str


class ReminderSaveRequest(BaseModel):
    invoice_id: int
    channel: str
    tone: str
    subject: str
    message_body: str
    was_edited: bool = False


class ReminderLogRead(BaseModel):
    id: int
    invoice_id: int
    invoice_number: str
    company_name: str
    channel: str
    tone: str
    subject: str
    message_body: str
    snapshot_balance_due: Optional[float] = None
    snapshot_interest: Optional[float] = None
    snapshot_total_claimable: Optional[float] = None
    delivery_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class TimelineEventRead(BaseModel):
    id: int
    invoice_id: int
    invoice_number: str
    event_type: str
    title: str
    details: str
    amount: Optional[float] = None
    balance_after: Optional[float] = None
    interest_snapshot: Optional[float] = None
    delivery_status: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NextActionItem(BaseModel):
    invoice_id: int
    invoice_number: str
    company_name: str
    action_type: str
    action_label: str
    priority_level: str
    priority_score: int
    balance_due: float
    msmed_interest: float
    days_overdue: int
    days_until_due: int
    visible_reason: str
    recommended_tone: str
    recommended_channel: str


class CashFlowScenarioBand(BaseModel):
    name: str
    expected_inflow_30d: float
    expected_principal_inflow_30d: float
    expected_interest_inflow_30d: float
    collection_share_of_outstanding_pct: float
    assumptions_summary: str
    bucket_breakdown: Dict[str, float]


class CashFlowScenariosReport(BaseModel):
    horizon_days: int
    total_current_outstanding: float
    total_accrued_interest: float
    conservative: CashFlowScenarioBand
    baseline: CashFlowScenarioBand
    optimistic: CashFlowScenarioBand
    historical_settled_invoices_count: int
    insufficient_historical_data: bool
    methodology_disclaimer: str


class EvidenceChecklistItem(BaseModel):
    item_key: str
    label: str
    status: str  # Available in System | User Verification Needed
    details: str


class InvoiceWorkspaceResponse(BaseModel):
    invoice: InvoiceComputed
    payments: List[PaymentRead]
    reminders: List[ReminderLogRead]
    timeline: List[TimelineEventRead]
    evidence_checklist: List[EvidenceChecklistItem]
    reconciliation_verified: bool
    legal_disclaimer: str
