# Implementation Roadmap — PayTrack AI

**Team Assumption:** 2 Student Developers  
**Current Status:** Phase 1 (Core MVP) & Phase 2 (Explainable Differentiator Suite) are **100% Implemented and Verified**.

---

## Phase 1: Core Receivables & Statutory Calculation MVP (Completed)
* **FastAPI + SQLite Backend ([`backend/app/`](file:///c:/Users/Raghavi/Documents/PayTrackAI/backend/app)):**
  * Customer directory with GSTIN, Udyam registration number, and 15/30/45-day credit SLA terms.
  * Invoice management with dynamic status calculation (`Pending`, `Partially Paid`, `Overdue`, `Paid`).
  * Indian Rupee (`₹`) Lakh/Crore formatting (`format_inr`).
  * Statutory MSMED Act Section 16 compound interest calculator (`3× RBI Bank Rate = 20.25% p.a.` with monthly rests) and Income Tax Section 43B(h) breach detection.
* **React + Vite + TypeScript Frontend ([`frontend/src/`](file:///c:/Users/Raghavi/Documents/PayTrackAI/frontend/src)):**
  * Clean, light-themed PitchFest executive dashboard, filterable invoice tracker, customer directory, payment recording modal, and reminder draft generator.

---

## Phase 2: High-Value Differentiator Suite (Completed in v2.0)
1. **Explainable Collection-Priority Engine ([`calculations.py`](file:///c:/Users/Raghavi/Documents/PayTrackAI/backend/app/services/calculations.py)):**
   * Deterministic `0–100` scoring engine combining Overdue Severity (`max 50 pts`), Principal Exposure (`max 30 pts`), and Follow-Up/Partial-Payment Status (`max 20 pts`).
   * User-configurable weights via `GET/PUT /api/priority-config` and the **Configure Score Weights** modal.
   * Removed unverified "AI reliability score" claims in favor of transparent observed ledger counts.
2. **Payment-Synchronized Reminders + Immutable Snapshots:**
   * Recording a partial payment immediately refreshes active reminder drafts with the updated remaining principal and recalculated Section 16 interest.
   * Historical logged reminders store immutable `snapshot_balance_due`, `snapshot_interest`, and `snapshot_total_claimable` fields so past audit records never silently mutate.
   * Explicit separation of `Drafted (Not Sent)`, `Draft Edited (Not Sent)`, and `Logged / Simulated (No Live Messaging Provider Connected)` statuses.
3. **Chronological Follow-Up Timeline & Evidence Readiness Workspace:**
   * New `InvoiceTimelineEvent` model tracking `INVOICE_CREATED`, `PAYMENT_RECEIVED`, `BALANCE_UPDATED`, `REMINDER_DRAFTED`, `REMINDER_EDITED`, and `REMINDER_LOGGED`.
   * Single-click **Timeline & Evidence Workspace** modal organizing invoice details, UTR payment reconciliation, reminder snapshots, and a 5-point administrative readiness checklist with a clear non-legal disclaimer.
4. **Daily Next-Best-Action Queue & Transparent 30-Day Cash-Flow Scenarios:**
   * Actionable queue surfacing pre-due nudges, unanswered reminder reviews, partial-payment reconciliations, and overdue escalations with visible reasons.
   * 30-day **Conservative**, **Baseline**, and **Optimistic** cash-inflow estimates with explicit aging-bucket recovery assumptions and an insufficient-historical-data warning banner.

---

## Phase 3: Next Release (Post-PitchFest — Weeks 1 to 6)
*Goal: Reduce manual data entry for real MSME pilots without requiring complex ERP integrations.*
1. **CSV / Excel & TallyPrime XML Import Wizard (Weeks 1–2):**
   * Allow MSME owners or their accountants to upload standard Tally/Zoho/Vyapar outstanding receivables exports (`.csv`, `.xlsx`, or Tally `.xml`) to bulk-create customers, invoices, and part-payments.
2. **PDF Invoice & Statement Attachment Storage (Weeks 3–4):**
   * Allow uploading PDF copies of GST tax invoices, purchase orders, and signed delivery challans/e-Way bills directly into the **Invoice Evidence & Follow-Up Workspace**, exporting a single zipped "Recovery Dossier" folder.
3. **Customer Expected-Payment Commitment Logging (Weeks 5–6):**
   * Allow owners to manually record a buyer's promised payment date (e.g., *"Buyer promised NEFT by 28 Oct on call"*) and trigger automatic next-action alerts if a promised date passes without a recorded UTR receipt.

---

## Phase 4: Future Integrations & Scale Validation (Months 2 to 6)
*Goal: Transition from copy-and-log assisted workflows to verified external delivery and empirical validation.*
1. **Opt-In WhatsApp Business API (WABA) & SMTP Email Integration:**
   * Integrate with an official Meta BSP (e.g., Interakt / Gupshup) and transactional email (AWS SES / Resend) so reminders transition from `Logged / Simulated` to `Sent` / `Delivered` / `Read` via signed webhook callbacks.
2. **UPI Payment Link & Auto-Reconciliation Webhook:**
   * Embed dynamic Razorpay/Cashfree UPI payment links inside reminders to automatically record `PAYMENT_RECEIVED` and `BALANCE_UPDATED` events upon settlement.
3. **Empirical Validation Study with 15–30 Local MSMEs:**
   * Before introducing any statistical or machine-learning payment-delay prediction model, collect permissioned, anonymized historical invoice-to-receipt data (minimum 200+ closed invoice cycles) to benchmark whether ML outperforms our transparent deterministic rule engine.
