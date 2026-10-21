# Sources and Assumptions — PayTrack AI

**Last Accessed / Verified Date:** October 20, 2026  
**Project Scope:** College PitchFest Prototype — Two-Person Student Engineering Team

---

## 1. Authoritative & Official Sources Consulted

### A. Statutory & Regulatory Framework (India)
1. **MSMED Act, 2006 (Chapter V — Delayed Payments to Micro and Small Enterprises, Sections 15–24):**
   * **Source:** Ministry of Micro, Small and Medium Enterprises (Government of India) — Official Act & MSME Samadhaan Portal
   * **URLs:**
     * `https://samadhaan.msme.gov.in/`
     * `https://msme.gov.in/`
   * **Accessed:** 2026-10-20
   * **Key Verified Provisions:**
     * **Section 15 (Liability of Buyer to Make Payment):** Credit period shall not exceed **15 days** where there is no written agreement, and shall not exceed **45 days** from the day of acceptance or deemed acceptance where a written agreement exists.
     * **Section 16 (Date from which and rate at which interest is payable):** Compound interest with **monthly rests** at **three times the Bank Rate** notified by the Reserve Bank of India (RBI).
     * **Section 23:** Interest payable or paid by the buyer under the MSMED Act is **not allowed as a deduction** for the computation of income under the Income Tax Act, 1961.

2. **Income Tax Act, 1961 — Section 43B(h) (Finance Act, 2023 Amendment):**
   * **Source:** Income Tax Department, Government of India
   * **URL:** `https://incometaxindia.gov.in/`
   * **Accessed:** 2026-10-20
   * **Key Verified Provision:** Any sum payable by an assessee to a Micro or Small enterprise beyond the time limit specified in Section 15 of the MSMED Act, 2006 (15 days without agreement / up to 45 days with agreement) is allowed as a tax deduction only in the financial year in which it is actually paid.

3. **Reserve Bank of India (RBI) Bank Rate Reference:**
   * **Source:** Reserve Bank of India Monetary Policy / Current Rates
   * **URL:** `https://www.rbi.org.in/`
   * **Accessed:** 2026-10-20
   * **Assumption Used in Prototype:** RBI Bank Rate is configured at **6.75% p.a.**, resulting in a statutory Section 16 MSMED interest rate of $3 \times 6.75\% = 20.25\%$ per annum compounded monthly.

---

### B. Competitor Product Documentation & Pricing Sources

1. **Zoho Books (India Edition) & Zoho Invoice (India Edition):**
   * **Official URLs:**
     * `https://www.zoho.com/in/books/`
     * `https://www.zoho.com/in/books/pricing/`
     * `https://www.zoho.com/in/invoice/`
     * `https://www.zoho.com/in/books/help/sales-invoices/payment-reminders.html`
   * **Accessed:** 2026-10-20
   * **Verified Findings:**
     * Zoho Invoice is free in India for invoicing, customer portal, partial payment recording, and scheduled/manual email reminders, but does not include full general-ledger cash-flow forecasting.
     * Zoho Books India offers a Free tier (turnover $\le$ ₹25 Lakh, up to 1,000 invoices/year) and paid plans starting from Standard (₹749/month billed annually or ₹899/month billed monthly + 18% GST) up to Ultimate (₹7,999/month billed annually + GST).

2. **TallyPrime (Tally Solutions Pvt. Ltd.):**
   * **Official URLs:**
     * `https://tallysolutions.com/tally-prime/`
     * `https://tallysolutions.com/tally-prime/pricing/`
     * `https://tallysolutions.com/tally-prime/whatsapp-for-business/`
     * `https://tallysolutions.com/us/msme-payment-rule-43b-h/`
   * **Accessed:** 2026-10-20
   * **Verified Findings:**
     * TallyPrime supports bill-wise receivables tracking, customizable aging buckets, interest calculation on overdue ledgers, MSME Section 43B(h) compliance reporting, and WhatsApp Business integration (via Interakt/WABA).
     * Pricing: TallyPrime Silver (Single user: ₹22,500 + 18% GST perpetual, or ₹750/month + GST rental); TallyPrime Gold (Multi-user: ₹67,500 + 18% GST perpetual, or ₹2,250/month + GST rental). Official WhatsApp add-on starts around ₹1,300/year + conversation wallet top-ups.

3. **ClearTax / Clear Finance Cloud:**
   * **Official URLs:**
     * `https://cleartax.in/`
     * `https://cleartax.in/s/msme-43bh-compliance`
   * **Accessed:** 2026-10-20
   * **Verified Findings:**
     * Primarily targets GST compliance, e-Invoicing, e-Way Bills, ITC reconciliation, and enterprise AP/AR automation, including vendor MSME 43B(h) compliance checks.

4. **CredFlow & Vyapar (Indian MSME Ecosystem):**
   * **Official URLs:**
     * `https://credflow.in/`
     * `https://vyaparapp.in/`
   * **Accessed:** 2026-10-20
   * **Verified Findings:**
     * **CredFlow** syncs with Tally/Busy via a desktop connector, automates multi-channel payment reminders (WhatsApp, SMS, Email, IVR), provides 30-day cash-flow projections, and offers a Collections CRM (plans up to ~₹19,999/year + GST for AI Accountant tier).
     * **Vyapar** focuses on mobile/desktop billing, inventory, and basic payment reminders for retail/trading micro-businesses.

---

## 2. Explicit Project Assumptions & Epistemic Boundaries

1. **Synthetic Demo Dataset Only:**
   * All 5 buyer companies, GSTINs, Udyam registration numbers, 8 invoices, and 5 historical UTR payment records in [`seed.py`](file:///c:/Users/Raghavi/Documents/PayTrackAI/backend/app/seed.py) are **synthetic demonstration data** created for the PitchFest prototype.
2. **Deterministic Rule Engine vs. Machine Learning:**
   * Because a prototype database has only 8 synthetic invoices (1 settled, 7 open), training a statistical or machine-learning credit risk or cash-flow prediction model would be scientifically invalid.
   * Therefore, **PayTrack AI intentionally uses a deterministic, transparent, configurable rule engine** for collection priority scoring and scenario-based cash-inflow estimates, and explicitly labels them as rule-based in both the API and UI.
3. **Simulated Reminder Logging vs. Live Messaging Delivery:**
   * To remain free and self-contained for a two-person student team without requiring paid Meta WhatsApp Business API (WABA) or SMTP credentials during the demo, reminders are generated as copy-ready drafts and logged locally with the status **`Logged / Simulated (No Live Messaging Provider Connected)`**. They are never labeled as verified external deliveries.
4. **Administrative Readiness vs. Legal Case Filing:**
   * PayTrack AI organizes invoice records, UTR payment reconciliations, immutable reminder snapshots, and an evidence checklist to help MSME owners prepare their internal documentation. It **does not** provide legal advice, does not automatically guarantee statutory eligibility under the MSMED Act, and does not submit filings directly to `samadhaan.msme.gov.in`.
5. **"Not Verified" Competitor Policy:**
   * Where internal algorithms or enterprise-tier features of closed-source commercial competitors (e.g., exact internal priority-scoring weights inside CredFlow's proprietary backend or custom Deluge scripts in Zoho Books) are not publicly documented, we explicitly classify them as **"Not Verified"** rather than assuming they do not exist.
