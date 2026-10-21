from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from .database import engine, Base, get_db, SessionLocal
from .models import Customer, Invoice, Payment, ReminderLog, InvoiceTimelineEvent
from .schemas import (
    PriorityWeightsConfig,
    CustomerCreate,
    CustomerRead,
    InvoiceCreate,
    InvoiceComputed,
    PaymentCreate,
    PaymentRead,
    ReminderDraftRequest,
    ReminderDraftResponse,
    ReminderSaveRequest,
    ReminderLogRead,
    TimelineEventRead,
    InvoiceWorkspaceResponse,
    CashFlowScenariosReport,
)
from .services.calculations import (
    compute_invoice_metrics,
    generate_reminder_draft,
    build_next_action_queue,
    compute_cashflow_scenarios,
    get_priority_weights,
    update_priority_weights,
    reset_priority_weights,
    format_inr,
)
from .seed import seed_database

# Create SQLite tables and seed/migrate synthetic Indian MSME demo data on startup
Base.metadata.create_all(bind=engine)
with SessionLocal() as db_init:
    seed_database(db_init, force_reset=False)

app = FastAPI(
    title="PayTrack AI — Explainable MSME Receivables Recovery Assistant",
    description=(
        "Backend API connecting invoice balances, deterministic collection priorities, "
        "payment-synchronized reminder drafts, immutable follow-up timelines, and transparent cash-flow scenarios."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "PayTrack AI Backend", "currency": "INR"}


@app.post("/api/reset-demo")
def reset_demo_data(db: Session = Depends(get_db)):
    reset_priority_weights()
    seed_database(db, force_reset=True)
    return {"message": "Demo data and priority weights reset to initial Indian MSME pitch state."}


@app.get("/api/priority-config")
def read_priority_config():
    return {
        "weights": get_priority_weights(),
        "scoring_method": "Deterministic Weighted Rule Engine (Not a trained ML model)",
        "documentation": {
            "overdue_max_points": "Maximum points contributed by days overdue (default 50).",
            "overdue_points_per_day": "Points added per overdue day up to overdue_max_points (default 1.0).",
            "pre_due_window_days": "Days before due date to trigger a pre-due reminder nudge (default 7).",
            "pre_due_points": "Points assigned when an unpaid invoice is within the pre-due window (default 12).",
            "amount_max_points": "Maximum points contributed by unpaid principal exposure (default 30).",
            "amount_reference_cap_inr": "Principal balance (₹) at which amount_max_points is reached (default ₹4,00,000).",
            "followup_max_points": "Maximum points contributed by follow-up gaps or partial-payment status (default 20).",
        },
    }


@app.put("/api/priority-config")
def save_priority_config(payload: PriorityWeightsConfig):
    updated = update_priority_weights(payload.model_dump())
    return {"weights": updated, "message": "Priority score weights updated."}


@app.post("/api/priority-config/reset")
def restore_default_priority_config():
    updated = reset_priority_weights()
    return {"weights": updated, "message": "Priority score weights reset to defaults."}


@app.get("/api/invoices", response_model=List[InvoiceComputed])
def list_invoices(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.due_date.asc()).all()
    computed = [compute_invoice_metrics(inv, inv.customer) for inv in invoices]
    computed.sort(key=lambda x: (-x["priority_score"], -x["days_overdue"], -x["balance_due"]))
    return computed


@app.post("/api/invoices", response_model=InvoiceComputed)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    if payload.due_date < payload.issue_date:
        raise HTTPException(
            status_code=400, detail="Due date cannot be earlier than the issue date."
        )

    customer = db.query(Customer).filter(Customer.id == payload.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    existing = db.query(Invoice).filter(Invoice.invoice_number == payload.invoice_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Invoice number already exists")

    new_inv = Invoice(
        invoice_number=payload.invoice_number,
        customer_id=payload.customer_id,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        total_amount=round(payload.total_amount, 2),
        amount_paid=0.0,
        description=payload.description,
        msme_agreement=payload.msme_agreement,
    )
    db.add(new_inv)
    db.commit()
    db.refresh(new_inv)

    db.add(
        InvoiceTimelineEvent(
            invoice_id=new_inv.id,
            event_type="INVOICE_CREATED",
            title=f"Invoice {new_inv.invoice_number} Issued ({format_inr(new_inv.total_amount)})",
            details=(
                f"Billed to {customer.company_name} for '{new_inv.description}'. "
                f"Due Date: {new_inv.due_date.strftime('%d %b %Y')} "
                f"({'45-day written MSME agreement' if new_inv.msme_agreement else '15-day statutory no-agreement SLA'})."
            ),
            amount=new_inv.total_amount,
            balance_after=new_inv.total_amount,
            interest_snapshot=0.0,
            delivery_status="Recorded in Ledger",
        )
    )
    db.commit()
    db.refresh(new_inv)
    return compute_invoice_metrics(new_inv, customer)


@app.get("/api/customers", response_model=List[CustomerRead])
def list_customers(db: Session = Depends(get_db)):
    customers = db.query(Customer).order_by(Customer.company_name.asc()).all()
    result = []
    for cust in customers:
        total_invoiced = 0.0
        total_paid = 0.0
        total_outstanding = 0.0
        overdue_amount = 0.0
        overdue_count = 0
        invoices_count = len(cust.invoices)
        paid_invoices_count = 0

        for inv in cust.invoices:
            m = compute_invoice_metrics(inv, cust)
            total_invoiced += m["total_amount"]
            total_paid += m["amount_paid"]
            total_outstanding += m["balance_due"]
            if m["status"] == "Overdue":
                overdue_amount += m["balance_due"]
                overdue_count += 1
            elif m["status"] == "Paid":
                paid_invoices_count += 1

        # Transparent observed ledger status (no unverified ML reliability inference)
        if overdue_count == 0 and total_outstanding == 0 and invoices_count > 0:
            risk_badge = "All Dues Settled"
        elif overdue_count == 0:
            risk_badge = "Current (No Overdues)"
        elif overdue_amount >= 250000 or any(
            compute_invoice_metrics(i, cust)["days_overdue"] > 45 for i in cust.invoices
        ):
            risk_badge = "Overdue >45d / High Exposure"
        else:
            risk_badge = "Active Overdue Balance"

        historical_note = (
            f"Observed across {invoices_count} invoice(s) ({paid_invoices_count} settled, {overdue_count} overdue). "
            f"Sample size <10 closed invoices; descriptive ledger metrics shown instead of predictive credit score."
        )

        result.append(
            {
                "id": cust.id,
                "name": cust.name,
                "company_name": cust.company_name,
                "gstin": cust.gstin,
                "udyam_number": cust.udyam_number,
                "email": cust.email,
                "phone": cust.phone,
                "city": cust.city,
                "credit_period_days": cust.credit_period_days,
                "reliability_score": cust.reliability_score,
                "total_invoiced": round(total_invoiced, 2),
                "total_paid": round(total_paid, 2),
                "total_outstanding": round(total_outstanding, 2),
                "overdue_amount": round(overdue_amount, 2),
                "overdue_invoices_count": overdue_count,
                "invoices_count": invoices_count,
                "paid_invoices_count": paid_invoices_count,
                "risk_badge": risk_badge,
                "historical_data_note": historical_note,
            }
        )
    return result


@app.post("/api/customers", response_model=CustomerRead)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    new_cust = Customer(
        name=payload.name,
        company_name=payload.company_name,
        gstin=payload.gstin.upper(),
        udyam_number=payload.udyam_number,
        email=payload.email,
        phone=payload.phone,
        city=payload.city,
        credit_period_days=payload.credit_period_days,
        reliability_score=80,
    )
    db.add(new_cust)
    db.commit()
    db.refresh(new_cust)
    return {
        "id": new_cust.id,
        "name": new_cust.name,
        "company_name": new_cust.company_name,
        "gstin": new_cust.gstin,
        "udyam_number": new_cust.udyam_number,
        "email": new_cust.email,
        "phone": new_cust.phone,
        "city": new_cust.city,
        "credit_period_days": new_cust.credit_period_days,
        "reliability_score": new_cust.reliability_score,
        "total_invoiced": 0.0,
        "total_paid": 0.0,
        "total_outstanding": 0.0,
        "overdue_amount": 0.0,
        "overdue_invoices_count": 0,
        "invoices_count": 0,
        "paid_invoices_count": 0,
        "risk_badge": "Current (No Overdues)",
        "historical_data_note": "New buyer account (0 historical invoices).",
    }


@app.get("/api/payments", response_model=List[PaymentRead])
def list_payments(db: Session = Depends(get_db)):
    payments = db.query(Payment).order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    return [
        {
            "id": p.id,
            "invoice_id": p.invoice_id,
            "invoice_number": p.invoice.invoice_number,
            "company_name": p.invoice.customer.company_name,
            "amount": round(p.amount, 2),
            "payment_date": p.payment_date,
            "payment_mode": p.payment_mode,
            "reference_number": p.reference_number,
            "notes": p.notes,
        }
        for p in payments
    ]


@app.post("/api/payments", response_model=PaymentRead)
def record_payment(payload: PaymentCreate, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than ₹0.")

    # Duplicate payment prevention: check if identical UTR/reference_number already exists on this invoice
    ref_clean = (payload.reference_number or "").strip()
    if ref_clean:
        dup_ref = (
            db.query(Payment)
            .filter(
                Payment.invoice_id == invoice.id,
                Payment.reference_number == ref_clean,
            )
            .first()
        )
        if dup_ref:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate payment reference '{ref_clean}' already recorded for {invoice.invoice_number}.",
            )

    current_metrics = compute_invoice_metrics(invoice, invoice.customer)
    prev_balance = current_metrics["balance_due"]

    if payload.amount > prev_balance + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Payment amount ({format_inr(payload.amount)}) exceeds remaining balance ({format_inr(prev_balance)}).",
        )

    payment = Payment(
        invoice_id=invoice.id,
        amount=round(payload.amount, 2),
        payment_date=payload.payment_date,
        payment_mode=payload.payment_mode,
        reference_number=ref_clean or None,
        notes=payload.notes,
    )
    db.add(payment)
    invoice.amount_paid = round(min(invoice.total_amount, current_metrics["amount_paid"] + payload.amount), 2)
    db.commit()
    db.refresh(invoice)
    db.refresh(payment)

    updated_metrics = compute_invoice_metrics(invoice, invoice.customer)
    new_balance = updated_metrics["balance_due"]
    new_interest = updated_metrics["msmed_interest"]

    # Record Payment Received & Balance Updated events in the chronological timeline
    db.add(
        InvoiceTimelineEvent(
            invoice_id=invoice.id,
            event_type="PAYMENT_RECEIVED",
            title=f"Payment Received: {format_inr(payment.amount)} via {payment.payment_mode}",
            details=(
                f"UTR / Ref: {payment.reference_number or 'N/A'}. "
                f"{payment.notes or 'Payment recorded in ledger.'}"
            ),
            amount=payment.amount,
            balance_after=new_balance,
            interest_snapshot=new_interest,
            delivery_status="Verified Ledger Receipt",
        )
    )
    db.add(
        InvoiceTimelineEvent(
            invoice_id=invoice.id,
            event_type="BALANCE_UPDATED",
            title=f"Principal Balance Updated: {format_inr(prev_balance)} → {format_inr(new_balance)}",
            details=(
                f"Remaining principal updated to {format_inr(new_balance)}; "
                f"recalculated MSMED Sec 16 interest is {format_inr(new_interest)} "
                f"(Total payable: {format_inr(updated_metrics['total_claimable'])})."
            ),
            amount=payment.amount,
            balance_after=new_balance,
            interest_snapshot=new_interest,
            delivery_status="Synchronized",
        )
    )
    db.commit()

    return {
        "id": payment.id,
        "invoice_id": payment.invoice_id,
        "invoice_number": invoice.invoice_number,
        "company_name": invoice.customer.company_name,
        "amount": payment.amount,
        "payment_date": payment.payment_date,
        "payment_mode": payment.payment_mode,
        "reference_number": payment.reference_number,
        "notes": payment.notes,
    }


@app.post("/api/reminders/draft", response_model=ReminderDraftResponse)
def create_reminder_draft(payload: ReminderDraftRequest, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    metrics = compute_invoice_metrics(invoice, invoice.customer)
    draft = generate_reminder_draft(metrics, payload.tone, payload.channel)

    if payload.log_draft_event:
        db.add(
            InvoiceTimelineEvent(
                invoice_id=invoice.id,
                event_type="REMINDER_DRAFTED",
                title=f"Reminder Draft Generated ({payload.tone} • {payload.channel})",
                details=(
                    f"Synchronized with live principal balance {format_inr(metrics['balance_due'])} "
                    f"+ MSMED interest {format_inr(metrics['msmed_interest'])}."
                ),
                amount=metrics["balance_due"],
                balance_after=metrics["balance_due"],
                interest_snapshot=metrics["msmed_interest"],
                delivery_status="Drafted (Not Sent)",
            )
        )
        db.commit()

    return draft


@app.post("/api/reminders/save", response_model=ReminderLogRead)
def save_reminder_log(payload: ReminderSaveRequest, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    metrics = compute_invoice_metrics(invoice, invoice.customer)
    sim_status = "Logged / Simulated (No Live Messaging Provider Connected)"

    # Store immutable historical snapshot of balance and interest at the time of logging
    log = ReminderLog(
        invoice_id=invoice.id,
        channel=payload.channel,
        tone=payload.tone,
        subject=payload.subject,
        message_body=payload.message_body,
        snapshot_balance_due=metrics["balance_due"],
        snapshot_interest=metrics["msmed_interest"],
        snapshot_total_claimable=metrics["total_claimable"],
        delivery_status=sim_status,
    )
    db.add(log)

    if payload.was_edited:
        db.add(
            InvoiceTimelineEvent(
                invoice_id=invoice.id,
                event_type="REMINDER_EDITED",
                title=f"Reminder Draft Customized by User ({payload.tone} • {payload.channel})",
                details=f"Edited subject/body before logging for balance {format_inr(metrics['balance_due'])}.",
                amount=metrics["balance_due"],
                balance_after=metrics["balance_due"],
                interest_snapshot=metrics["msmed_interest"],
                delivery_status="Draft Edited (Not Sent)",
            )
        )

    db.add(
        InvoiceTimelineEvent(
            invoice_id=invoice.id,
            event_type="REMINDER_LOGGED",
            title=f"{payload.tone} {payload.channel} Reminder Logged (Snapshot: {format_inr(metrics['balance_due'])})",
            details=(
                f"Subject: {payload.subject} | Immutable Snapshot Principal: {format_inr(metrics['balance_due'])}, "
                f"Interest: {format_inr(metrics['msmed_interest'])}, Total: {format_inr(metrics['total_claimable'])}."
            ),
            amount=metrics["balance_due"],
            balance_after=metrics["balance_due"],
            interest_snapshot=metrics["msmed_interest"],
            delivery_status=sim_status,
        )
    )

    db.commit()
    db.refresh(log)

    return {
        "id": log.id,
        "invoice_id": log.invoice_id,
        "invoice_number": invoice.invoice_number,
        "company_name": invoice.customer.company_name,
        "channel": log.channel,
        "tone": log.tone,
        "subject": log.subject,
        "message_body": log.message_body,
        "snapshot_balance_due": log.snapshot_balance_due,
        "snapshot_interest": log.snapshot_interest,
        "snapshot_total_claimable": log.snapshot_total_claimable,
        "delivery_status": log.delivery_status,
        "created_at": log.created_at,
    }


@app.get("/api/reminders", response_model=List[ReminderLogRead])
def list_reminders(db: Session = Depends(get_db)):
    logs = db.query(ReminderLog).order_by(ReminderLog.created_at.desc(), ReminderLog.id.desc()).all()
    return [
        {
            "id": l.id,
            "invoice_id": l.invoice_id,
            "invoice_number": l.invoice.invoice_number,
            "company_name": l.invoice.customer.company_name,
            "channel": l.channel,
            "tone": l.tone,
            "subject": l.subject,
            "message_body": l.message_body,
            "snapshot_balance_due": l.snapshot_balance_due,
            "snapshot_interest": l.snapshot_interest,
            "snapshot_total_claimable": l.snapshot_total_claimable,
            "delivery_status": l.delivery_status
            or "Logged / Simulated (No Live Messaging Provider Connected)",
            "created_at": l.created_at,
        }
        for l in logs
    ]


@app.get("/api/invoices/{invoice_id}/timeline", response_model=List[TimelineEventRead])
def get_invoice_timeline(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    events = (
        db.query(InvoiceTimelineEvent)
        .filter(InvoiceTimelineEvent.invoice_id == invoice_id)
        .order_by(InvoiceTimelineEvent.created_at.asc(), InvoiceTimelineEvent.id.asc())
        .all()
    )
    return [
        {
            "id": ev.id,
            "invoice_id": ev.invoice_id,
            "invoice_number": invoice.invoice_number,
            "event_type": ev.event_type,
            "title": ev.title,
            "details": ev.details,
            "amount": ev.amount,
            "balance_after": ev.balance_after,
            "interest_snapshot": ev.interest_snapshot,
            "delivery_status": ev.delivery_status,
            "created_at": ev.created_at,
        }
        for ev in events
    ]


@app.get("/api/invoices/{invoice_id}/workspace", response_model=InvoiceWorkspaceResponse)
def get_invoice_workspace(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    metrics = compute_invoice_metrics(invoice, invoice.customer)
    payments_list = [
        {
            "id": p.id,
            "invoice_id": p.invoice_id,
            "invoice_number": invoice.invoice_number,
            "company_name": invoice.customer.company_name,
            "amount": round(p.amount, 2),
            "payment_date": p.payment_date,
            "payment_mode": p.payment_mode,
            "reference_number": p.reference_number,
            "notes": p.notes,
        }
        for p in sorted(invoice.payments, key=lambda x: (x.payment_date, x.id))
    ]

    reminders_list = [
        {
            "id": r.id,
            "invoice_id": r.invoice_id,
            "invoice_number": invoice.invoice_number,
            "company_name": invoice.customer.company_name,
            "channel": r.channel,
            "tone": r.tone,
            "subject": r.subject,
            "message_body": r.message_body,
            "snapshot_balance_due": r.snapshot_balance_due,
            "snapshot_interest": r.snapshot_interest,
            "snapshot_total_claimable": r.snapshot_total_claimable,
            "delivery_status": r.delivery_status
            or "Logged / Simulated (No Live Messaging Provider Connected)",
            "created_at": r.created_at,
        }
        for r in sorted(invoice.reminders, key=lambda x: (x.created_at, x.id), reverse=True)
    ]

    timeline_list = get_invoice_timeline(invoice_id, db)

    sum_payments = round(sum(p["amount"] for p in payments_list), 2)
    reconciliation_verified = abs((metrics["total_amount"] - sum_payments) - metrics["balance_due"]) <= 0.01

    evidence_checklist = [
        {
            "item_key": "tax_invoice_record",
            "label": "GST Tax Invoice & Buyer GSTIN Record",
            "status": "Available in System",
            "details": f"Invoice {invoice.invoice_number} ({format_inr(metrics['total_amount'])}) • Buyer GSTIN: {invoice.customer.gstin}",
        },
        {
            "item_key": "credit_sla_terms",
            "label": "MSMED Section 15 Credit Term Documentation",
            "status": "Available in System",
            "details": (
                f"Written agreement recorded ({metrics['statutory_limit_days']}-day statutory limit; "
                f"Due: {invoice.due_date.strftime('%d %b %Y')})"
                if invoice.msme_agreement
                else "No written credit agreement flagged (15-day statutory limit applies)"
            ),
        },
        {
            "item_key": "payment_utr_reconciliation",
            "label": "Part-Payment & UTR Ledger Reconciliation",
            "status": "Available in System" if reconciliation_verified else "User Verification Needed",
            "details": (
                f"{len(payments_list)} receipt(s) totaling {format_inr(sum_payments)} reconciled against "
                f"{format_inr(metrics['total_amount'])} billed -> {format_inr(metrics['balance_due'])} unpaid."
            ),
        },
        {
            "item_key": "followup_communication_trail",
            "label": "Timestamped Follow-Up & Reminder Snapshot Log",
            "status": "Available in System" if len(reminders_list) > 0 else "User Verification Needed",
            "details": (
                f"{len(reminders_list)} logged reminder snapshot(s) on file (Note: logged locally; external delivery receipt requires live messaging provider)."
                if len(reminders_list) > 0
                else "No formal reminders logged yet for this invoice."
            ),
        },
        {
            "item_key": "external_delivery_proof",
            "label": "Signed Delivery Challan / e-Way Bill / Buyer Acceptance Proof",
            "status": "User Verification Needed",
            "details": "External physical/PDF proof of goods delivery or service acceptance must be maintained by the supplier.",
        },
    ]

    return {
        "invoice": metrics,
        "payments": payments_list,
        "reminders": reminders_list,
        "timeline": timeline_list,
        "evidence_checklist": evidence_checklist,
        "reconciliation_verified": reconciliation_verified,
        "legal_disclaimer": (
            "ADMINISTRATIVE READINESS DISCLAIMER: This workspace organizes internal commercial, payment, and follow-up records "
            "for small-business workflow clarity. It does not constitute legal advice, does not automatically verify or establish "
            "statutory eligibility under the MSMED Act, 2006 or Section 43B(h) of the Income Tax Act, and is not a legal case-filing system."
        ),
    }


@app.get("/api/cashflow-scenarios", response_model=CashFlowScenariosReport)
def get_cashflow_scenarios(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).all()
    computed = [compute_invoice_metrics(inv, inv.customer) for inv in invoices]
    return compute_cashflow_scenarios(computed, horizon_days=30)


@app.get("/api/dashboard")
def get_dashboard_summary(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).all()
    computed = [compute_invoice_metrics(inv, inv.customer) for inv in invoices]

    total_invoiced = round(sum(i["total_amount"] for i in computed), 2)
    total_collected = round(sum(i["amount_paid"] for i in computed), 2)
    total_outstanding = round(sum(i["balance_due"] for i in computed), 2)
    total_overdue = round(sum(i["balance_due"] for i in computed if i["status"] == "Overdue"), 2)
    total_current_not_due = round(
        sum(i["balance_due"] for i in computed if i["balance_due"] > 0 and i["status"] != "Overdue"),
        2,
    )
    total_msmed_interest = round(sum(i["msmed_interest"] for i in computed), 2)
    section_43bh_count = sum(1 for i in computed if i["section_43bh_at_risk"])
    overdue_invoices_count = sum(1 for i in computed if i["status"] == "Overdue")
    current_not_due_count = sum(
        1 for i in computed if i["balance_due"] > 0 and i["status"] != "Overdue"
    )
    open_invoices_count = overdue_invoices_count + current_not_due_count
    collection_rate = round((total_collected / total_invoiced * 100.0), 1) if total_invoiced > 0 else 0.0

    buckets = {
        "Current (Not Due)": 0.0,
        "1–15 Days": 0.0,
        "16–30 Days": 0.0,
        "31–45 Days": 0.0,
        "45+ Days Overdue": 0.0,
    }
    bucket_counts = {k: 0 for k in buckets}

    for i in computed:
        b = i["aging_bucket"]
        if b in buckets:
            buckets[b] = round(buckets[b] + i["balance_due"], 2)
            bucket_counts[b] += 1

    aging_breakdown = [
        {"bucket": k, "amount": v, "count": bucket_counts[k]} for k, v in buckets.items()
    ]

    priority_queue = sorted(
        [i for i in computed if i["balance_due"] > 0],
        key=lambda x: (-x["priority_score"], -x["days_overdue"], -x["balance_due"]),
    )[:6]

    next_action_queue = build_next_action_queue(computed)
    cashflow_scenarios = compute_cashflow_scenarios(computed, horizon_days=30)

    return {
        "kpis": {
            "total_invoiced": total_invoiced,
            "total_collected": total_collected,
            "total_outstanding": total_outstanding,
            "total_overdue": total_overdue,
            "total_current_not_due": total_current_not_due,
            "total_msmed_interest": total_msmed_interest,
            "total_claimable_with_interest": round(total_outstanding + total_msmed_interest, 2),
            "collection_rate": collection_rate,
            "open_invoices_count": open_invoices_count,
            "overdue_invoices_count": overdue_invoices_count,
            "current_not_due_count": current_not_due_count,
            "section_43bh_count": section_43bh_count,
            "rbi_bank_rate_percent": 6.75,
            "msmed_statutory_rate_percent": 20.25,
            "statutory_assumptions_note": (
                "Verified Legal Rules: MSMED Act Sec 15 mandates payment within 15 days (no written agreement) or up to 45 days (written agreement) from acceptance; "
                "Sec 16 mandates compound interest with monthly rests at 3× RBI Bank Rate; Income Tax Act Sec 43B(h) links buyer tax deduction to Sec 15 timelines. "
                "Prototype Assumptions: Invoice issue_date is used as a proxy for acceptance date for the 15d/45d Sec 43B(h) indicator; Sec 16 interest is estimated from due_date using a 6.75% RBI Bank Rate assumption (20.25% p.a.). Estimates are for operational illustration, not legal advice."
            ),
        },
        "aging_breakdown": aging_breakdown,
        "priority_queue": priority_queue,
        "next_action_queue": next_action_queue,
        "cashflow_scenarios": cashflow_scenarios,
        "priority_weights": get_priority_weights(),
    }
