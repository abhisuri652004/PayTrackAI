# Validation and Testing Report — PayTrack AI

**Test Suite Location:** [`backend/validate_calculations.py`](file:///c:/Users/Raghavi/Documents/PayTrackAI/backend/validate_calculations.py)  
**Frontend Type & Build Check:** `npm run build` (`tsc -b && vite build` in [`frontend/`](file:///c:/Users/Raghavi/Documents/PayTrackAI/frontend))

---

## 1. Pre-Implementation Audit of Existing Application Inconsistencies

Before implementing the Phase 2 differentiator features, we audited the existing codebase against the 6 consistency criteria in Section E:

1. **Current Balance vs. Historical Reminder Balance:**
   * *Finding:* Previously, `ReminderLog` only stored `message_body` text without structured `snapshot_balance_due`, `snapshot_interest`, or `snapshot_total_claimable` columns, and the frontend `useEffect` did not re-fetch active drafts when a partial payment changed an invoice's `balance_due`.
   * *Resolution:* Added `snapshot_balance_due`, `snapshot_interest`, and `snapshot_total_claimable` to [`ReminderLog`](file:///c:/Users/Raghavi/Documents/PayTrackAI/backend/app/models.py#L64-L82) and updated [`App.tsx`](file:///c:/Users/Raghavi/Documents/PayTrackAI/frontend/src/App.tsx#L140-L157) to automatically regenerate active drafts whenever `balance_due`, `amount_paid`, or `payments.length` changes while keeping historical reminder logs immutable.
2. **Invoice Totals vs. Recorded Payments & Payment Ledger vs. Invoice Balance:**
   * *Finding:* Previously, `compute_invoice_metrics` read `invoice.amount_paid` directly without cross-checking `invoice.payments` or blocking duplicate UTR reference numbers.
   * *Resolution:* Updated [`compute_invoice_metrics`](file:///c:/Users/Raghavi/Documents/PayTrackAI/backend/app/services/calculations.py#L97-L108) to reconcile `amount_paid` against the sum of recorded `Payment` entries, added duplicate `reference_number` (UTR) rejection in [`record_payment`](file:///c:/Users/Raghavi/Documents/PayTrackAI/backend/app/main.py#L298-L315), and added a `reconciliation_verified` check in the Invoice Workspace endpoint.
3. **Interest, Priority & Statutory Labels:**
   * *Finding:* Previously, `Customer.reliability_score` was used in priority scoring and labeled as an "AI Reliability Score" despite having only 1–2 synthetic invoices per buyer.
   * *Resolution:* Removed `reliability_score` from priority calculation in [`calculations.py`](file:///c:/Users/Raghavi/Documents/PayTrackAI/backend/app/services/calculations.py#L145-L245), replaced it with a transparent 3-factor deterministic formula (`Overdue Severity + Balance Exposure + Follow-Up/Partial Status`), and updated the Customer Directory to show observed invoice counts with an explicit small-sample note.

---

## 2. Automated Test Coverage Matrix (11 Test Suites)

| Suite # | Test Category | What Is Tested & Asserted | Status |
| :---: | :--- | :--- | :---: |
| **1** | **INR Currency Formatting** | Lakh/Crore grouping (`₹4,85,000`, `₹1,25,00,000.50`, `₹0`, negative values). | **PASS** |
| **2** | **Overdue Days & MSMED Sec 16 Interest** | Monthly-compounded interest at `20.25% p.a.` (`3× RBI 6.75% rate`): `₹4,00,000` @ 62 days $\to$ `₹14,072.85`; `0` days overdue $\to$ `₹0.00`; negative/zero principal $\to$ `₹0.00`. | **PASS** |
| **3** | **Priority-Score Consistency, Configurable Weights & Bullet Sum** | Identical inputs produce identical `0–100` scores; `total_score == overdue_points + amount_points + followup_points`; every `+X pts` bullet in `factors` sums **exactly** to `total_score` (both under default weights and when custom sub-weights hit the `followup_max` cap). | **PASS** |
| **4** | **Partial-Payment Balance & Reminder Synchronization** | Recording a `₹10,000` partial payment on `INV-2026-101` reduces `balance_due` from `₹4,00,000` to `₹3,90,000`, recalculates interest to `₹13,721.03` and total payable to `₹4,03,721.03`, and updates `Polite`, `Firm`, and `Statutory MSME` drafts with zero stale `₹4,00,000` text. | **PASS** |
| **5** | **Duplicate-Payment & Overpayment Prevention** | Submitting a second payment with the same UTR (`UPI-TEST-990011`) on the same invoice raises `HTTP 400 Bad Request`; submitting `₹5,00,000` against `₹3,90,000` balance raises `HTTP 400`. | **PASS** |
| **6** | **Historical Reminder Snapshot Preservation** | After recording a `₹10,000` partial payment and logging a new `₹3,90,000` reminder, the earlier seeded reminder log on `INV-2026-101` retains `snapshot_balance_due == 400000.0` (`₹4,00,000`) without silent mutation. | **PASS** |
| **7** | **Separation of Drafted, Edited & Simulated Statuses + Timeline** | Verifies drafts are labeled `Drafted (Not Sent)`, edited drafts log `REMINDER_EDITED` (`Draft Edited (Not Sent)`), and saved logs are labeled `Logged / Simulated (No Live Messaging Provider Connected)` — never falsely labeled `Delivered`. Verifies all 6 timeline event types (`INVOICE_CREATED`, `PAYMENT_RECEIVED`, `BALANCE_UPDATED`, `REMINDER_DRAFTED`, `REMINDER_EDITED`, `REMINDER_LOGGED`). | **PASS** |
| **8** | **Next-Best-Action Queue & All-Invoice Bullet Sums** | Verifies all 4 action types (`REVIEW_UNANSWERED_REMINDER`, `RECONCILE_PARTIAL_PAYMENT`, `FOLLOW_UP_OVERDUE`, `SEND_PRE_DUE_REMINDER`) and asserts exact bullet-point sums across all open invoices. | **PASS** |
| **9** | **Transparent 30-Day Cash-Flow Scenarios (Principal vs. Interest)** | Verifies `0 < Conservative <= Baseline <= Optimistic`, asserts `expected_principal_inflow_30d + expected_interest_inflow_30d == expected_inflow_30d`, and verifies `collection_share_of_outstanding_pct` is calculated strictly against principal. | **PASS** |
| **10** | **Empty & Insufficient Historical Data** | Verifies `compute_cashflow_scenarios([])` and `build_next_action_queue([])` return `0.0` / `[]` without division-by-zero errors, and `<10` settled invoices sets `insufficient_historical_data = True`. | **PASS** |
| **11** | **Boundary Values & Live Database (`paytrack.db`) Reconciliation** | Verifies `15`-day vs `45`-day boundary, exact full settlement, invalid dates/amounts, and reconciles the live `paytrack.db` (`Total Outstanding ₹14,55,000 == Overdue ₹11,53,000 + Current Not Due ₹3,02,000 == Sum of Aging Buckets`). | **PASS** |
