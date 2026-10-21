from datetime import date, datetime, time, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from .models import Customer, Invoice, Payment, ReminderLog, InvoiceTimelineEvent
from .services.calculations import calculate_msmed_compound_interest, format_inr


def ensure_schema_and_backfill(db: Session):
    """
    Non-destructively migrates existing SQLite tables if columns were added
    and backfills timeline events/snapshots if missing, without altering existing payment records.
    """
    # Check and add new columns on reminder_logs if upgrading an existing paytrack.db
    existing_cols = [
        row[1] for row in db.execute(text("PRAGMA table_info(reminder_logs)")).fetchall()
    ]
    migrations = [
        ("snapshot_balance_due", "FLOAT"),
        ("snapshot_interest", "FLOAT"),
        ("snapshot_total_claimable", "FLOAT"),
        (
            "delivery_status",
            " VARCHAR(80) DEFAULT 'Logged / Simulated (No Live Messaging Provider Connected)'",
        ),
    ]
    for col_name, col_type in migrations:
        if col_name not in existing_cols:
            db.execute(text(f"ALTER TABLE reminder_logs ADD COLUMN {col_name} {col_type}"))
    db.commit()

    # Backfill snapshot fields on existing reminder logs if null
    logs = db.query(ReminderLog).all()
    for log in logs:
        if log.snapshot_balance_due is None and log.invoice:
            # Historical snapshot for seeded INV-2026-101 was ₹4,00,000, INV-2026-102 was ₹3,20,000
            if log.invoice.invoice_number == "INV-2026-101":
                snap_bal = 400000.0
                days_ov = max(0, (date.today() - log.invoice.due_date).days)
            else:
                snap_bal = round(max(0.0, log.invoice.total_amount - log.invoice.amount_paid), 2)
                days_ov = max(0, (date.today() - log.invoice.due_date).days)
            snap_int = calculate_msmed_compound_interest(snap_bal, days_ov)
            log.snapshot_balance_due = snap_bal
            log.snapshot_interest = snap_int
            log.snapshot_total_claimable = round(snap_bal + snap_int, 2)
        if not log.delivery_status:
            log.delivery_status = "Logged / Simulated (No Live Messaging Provider Connected)"
    db.commit()

    # Backfill timeline events if empty
    has_events = db.query(InvoiceTimelineEvent).first()
    if not has_events:
        _populate_timeline_from_existing_records(db)


def _populate_timeline_from_existing_records(db: Session):
    invoices = db.query(Invoice).all()
    for inv in invoices:
        issue_dt = datetime.combine(inv.issue_date, time(9, 30))
        db.add(
            InvoiceTimelineEvent(
                invoice_id=inv.id,
                event_type="INVOICE_CREATED",
                title=f"Invoice {inv.invoice_number} Issued ({format_inr(inv.total_amount)})",
                details=(
                    f"Billed to {inv.customer.company_name} for '{inv.description}'. "
                    f"Due Date: {inv.due_date.strftime('%d %b %Y')} "
                    f"({'45-day written MSME agreement' if inv.msme_agreement else '15-day statutory no-agreement SLA'})."
                ),
                amount=inv.total_amount,
                balance_after=inv.total_amount,
                interest_snapshot=0.0,
                delivery_status="Recorded in Ledger",
                created_at=issue_dt,
            )
        )

        running_balance = float(inv.total_amount)
        sorted_payments = sorted(inv.payments, key=lambda p: (p.payment_date, p.id))
        for idx, pay in enumerate(sorted_payments):
            pay_dt = datetime.combine(pay.payment_date, time(14, 15)) + timedelta(minutes=idx * 5)
            prev_balance = running_balance
            running_balance = round(max(0.0, running_balance - float(pay.amount)), 2)
            days_ov_at_pay = max(0, (pay.payment_date - inv.due_date).days) if running_balance > 0 else 0
            int_after = calculate_msmed_compound_interest(running_balance, days_ov_at_pay)

            db.add(
                InvoiceTimelineEvent(
                    invoice_id=inv.id,
                    event_type="PAYMENT_RECEIVED",
                    title=f"Payment Received: {format_inr(pay.amount)} via {pay.payment_mode}",
                    details=(
                        f"UTR / Ref: {pay.reference_number or 'N/A'}. "
                        f"{pay.notes or 'Payment recorded against invoice.'}"
                    ),
                    amount=pay.amount,
                    balance_after=running_balance,
                    interest_snapshot=int_after,
                    delivery_status="Verified Ledger Receipt",
                    created_at=pay_dt,
                )
            )
            db.add(
                InvoiceTimelineEvent(
                    invoice_id=inv.id,
                    event_type="BALANCE_UPDATED",
                    title=f"Principal Balance Updated: {format_inr(prev_balance)} → {format_inr(running_balance)}",
                    details=(
                        f"Remaining principal recalculated to {format_inr(running_balance)} "
                        f"({'Settled' if running_balance == 0 else 'Open balance'})."
                    ),
                    amount=pay.amount,
                    balance_after=running_balance,
                    interest_snapshot=int_after,
                    delivery_status="Synchronized",
                    created_at=pay_dt + timedelta(seconds=30),
                )
            )

        for r_idx, rem in enumerate(inv.reminders):
            snap_bal = rem.snapshot_balance_due if rem.snapshot_balance_due is not None else running_balance
            snap_int = rem.snapshot_interest if rem.snapshot_interest is not None else 0.0
            db.add(
                InvoiceTimelineEvent(
                    invoice_id=inv.id,
                    event_type="REMINDER_LOGGED",
                    title=f"{rem.tone} {rem.channel} Reminder Logged (Snapshot: {format_inr(snap_bal)})",
                    details=(
                        f"Subject: {rem.subject} | Immutable Snapshot Principal: {format_inr(snap_bal)}, "
                        f"Accrued Interest: {format_inr(snap_int)}."
                    ),
                    amount=snap_bal,
                    balance_after=snap_bal,
                    interest_snapshot=snap_int,
                    delivery_status=rem.delivery_status
                    or "Logged / Simulated (No Live Messaging Provider Connected)",
                    created_at=rem.created_at or (datetime.utcnow() - timedelta(days=2 - r_idx)),
                )
            )
    db.commit()


def seed_database(db: Session, force_reset: bool = False):
    """Seeds the SQLite database with realistic Indian MSME customers, invoices, payments, reminders, and timeline events."""
    if force_reset:
        db.query(InvoiceTimelineEvent).delete()
        db.query(ReminderLog).delete()
        db.query(Payment).delete()
        db.query(Invoice).delete()
        db.query(Customer).delete()
        db.commit()
    else:
        existing = db.query(Customer).first()
        if existing:
            ensure_schema_and_backfill(db)
            return

    today = date.today()

    customers = [
        Customer(
            name="Rajesh Deshmukh",
            company_name="Bharat Precision Auto Components Pvt Ltd",
            gstin="27AABCB4821M1Z5",
            udyam_number="UDYAM-MH-26-0048192",
            email="accounts@bharatauto.co.in",
            phone="+91 98230 44120",
            city="Pune, Maharashtra",
            credit_period_days=30,
            reliability_score=48,
        ),
        Customer(
            name="Meenakshi Sundaram",
            company_name="Cauvery Industrial Textiles & Yarns Ltd",
            gstin="33AAACC7192K1Z9",
            udyam_number="UDYAM-TN-03-0019481",
            email="finance@cauverytextiles.in",
            phone="+91 94431 78210",
            city="Coimbatore, Tamil Nadu",
            credit_period_days=45,
            reliability_score=74,
        ),
        Customer(
            name="Vikramaditya Reddy",
            company_name="Deccan Infra & Structural Steels LLP",
            gstin="36AABCD8931F1Z2",
            udyam_number="UDYAM-TS-07-0083120",
            email="ap@deccaninfrasteel.com",
            phone="+91 90001 56239",
            city="Hyderabad, Telangana",
            credit_period_days=30,
            reliability_score=39,
        ),
        Customer(
            name="Ananya Sharma",
            company_name="Namma Electronics & PCB Assemblies Pvt Ltd",
            gstin="29AABCN3390Q1Z4",
            udyam_number="UDYAM-KR-03-0059104",
            email="billing@nammaelectronics.io",
            phone="+91 99801 11290",
            city="Bengaluru, Karnataka",
            credit_period_days=30,
            reliability_score=91,
        ),
        Customer(
            name="Harshad Patel",
            company_name="Sabarmati Agro Packaging & Polymers",
            gstin="24AAECS6402H1Z8",
            udyam_number="UDYAM-GJ-01-0032198",
            email="purchase@sabarmatipack.com",
            phone="+91 98250 67321",
            city="Ahmedabad, Gujarat",
            credit_period_days=15,
            reliability_score=62,
        ),
    ]

    db.add_all(customers)
    db.commit()
    for c in customers:
        db.refresh(c)

    invoices = [
        # 1. Critical >45 days overdue (Sec 43B(h) triggered)
        Invoice(
            invoice_number="INV-2026-101",
            customer_id=customers[2].id,  # Deccan Infra
            issue_date=today - timedelta(days=92),
            due_date=today - timedelta(days=62),
            total_amount=485000.0,
            amount_paid=85000.0,
            description="CNC Machined Heavy Flange Assemblies (Batch #44A)",
            msme_agreement=True,
        ),
        # 2. Critical >45 days overdue
        Invoice(
            invoice_number="INV-2026-102",
            customer_id=customers[0].id,  # Bharat Precision Auto
            issue_date=today - timedelta(days=78),
            due_date=today - timedelta(days=48),
            total_amount=320000.0,
            amount_paid=0.0,
            description="High-Tensile Gearbox Shafts & Heat Treatment (600 Units)",
            msme_agreement=True,
        ),
        # 3. 31-45 Days Overdue
        Invoice(
            invoice_number="INV-2026-103",
            customer_id=customers[4].id,  # Sabarmati Agro
            issue_date=today - timedelta(days=52),
            due_date=today - timedelta(days=37),
            total_amount=145000.0,
            amount_paid=45000.0,
            description="Industrial Conveying Rollers & Sprocket Kit",
            msme_agreement=False,  # 15-day statutory limit without written agreement
        ),
        # 4. 16-30 Days Overdue
        Invoice(
            invoice_number="INV-2026-104",
            customer_id=customers[1].id,  # Cauvery Textiles
            issue_date=today - timedelta(days=67),
            due_date=today - timedelta(days=22),
            total_amount=275000.0,
            amount_paid=100000.0,
            description="Automated Loom Spindle Bearings & Alu-Extrusions",
            msme_agreement=True,
        ),
        # 5. 1-15 Days Overdue
        Invoice(
            invoice_number="INV-2026-105",
            customer_id=customers[0].id,  # Bharat Precision Auto
            issue_date=today - timedelta(days=39),
            due_date=today - timedelta(days=9),
            total_amount=168000.0,
            amount_paid=0.0,
            description="Precision Die-Cast Aluminum Housings (Lot 19)",
            msme_agreement=True,
        ),
        # 6. Pending (Due in 4 days)
        Invoice(
            invoice_number="INV-2026-106",
            customer_id=customers[3].id,  # Namma Electronics
            issue_date=today - timedelta(days=26),
            due_date=today + timedelta(days=4),
            total_amount=210000.0,
            amount_paid=110000.0,
            description="Anodized Heat Sink Enclosures for EV Chargers",
            msme_agreement=True,
        ),
        # 7. Pending (Due in 18 days)
        Invoice(
            invoice_number="INV-2026-107",
            customer_id=customers[1].id,  # Cauvery Textiles
            issue_date=today - timedelta(days=27),
            due_date=today + timedelta(days=18),
            total_amount=192000.0,
            amount_paid=0.0,
            description="Stainless Steel Guide Rollers & Mounting Brackets",
            msme_agreement=True,
        ),
        # 8. Fully Paid Invoice
        Invoice(
            invoice_number="INV-2026-108",
            customer_id=customers[3].id,  # Namma Electronics
            issue_date=today - timedelta(days=45),
            due_date=today - timedelta(days=15),
            total_amount=340000.0,
            amount_paid=340000.0,
            description="Sheet Metal Server Rack Chassis (120 Units)",
            msme_agreement=True,
        ),
    ]

    db.add_all(invoices)
    db.commit()
    for inv in invoices:
        db.refresh(inv)

    payments = [
        Payment(
            invoice_id=invoices[0].id,
            amount=85000.0,
            payment_date=today - timedelta(days=40),
            payment_mode="NEFT",
            reference_number="HDFCN2619844210",
            notes="Part payment against Batch #44A",
        ),
        Payment(
            invoice_id=invoices[2].id,
            amount=45000.0,
            payment_date=today - timedelta(days=25),
            payment_mode="UPI",
            reference_number="UPI-628910443129",
            notes="Advance settlement via Corporate UPI",
        ),
        Payment(
            invoice_id=invoices[3].id,
            amount=100000.0,
            payment_date=today - timedelta(days=14),
            payment_mode="RTGS",
            reference_number="SBINR52026091822",
            notes="First tranche cleared",
        ),
        Payment(
            invoice_id=invoices[5].id,
            amount=110000.0,
            payment_date=today - timedelta(days=10),
            payment_mode="NEFT",
            reference_number="ICICN2628199301",
            notes="50%+ milestone payment on delivery",
        ),
        Payment(
            invoice_id=invoices[7].id,
            amount=340000.0,
            payment_date=today - timedelta(days=18),
            payment_mode="RTGS",
            reference_number="AXISR2600984120",
            notes="Full settlement before due date",
        ),
    ]

    db.add_all(payments)
    db.commit()

    inv1_int = calculate_msmed_compound_interest(400000.0, 62)
    inv2_int = calculate_msmed_compound_interest(320000.0, 48)

    reminders = [
        ReminderLog(
            invoice_id=invoices[0].id,
            channel="Email",
            tone="Statutory MSME",
            subject="STATUTORY NOTICE u/s 15 & 16 of MSMED Act 2006 & Sec 43B(h): Invoice INV-2026-101",
            message_body="Formal intimation issued regarding ₹4,00,000 overdue balance + 20.25% compound interest under Section 16 of MSMED Act.",
            snapshot_balance_due=400000.0,
            snapshot_interest=inv1_int,
            snapshot_total_claimable=round(400000.0 + inv1_int, 2),
            delivery_status="Logged / Simulated (No Live Messaging Provider Connected)",
            created_at=datetime.utcnow() - timedelta(days=5),
        ),
        ReminderLog(
            invoice_id=invoices[1].id,
            channel="WhatsApp",
            tone="Firm",
            subject="OVERDUE ALERT: Immediate Payment Requested for Invoice INV-2026-102",
            message_body="Urgent WhatsApp follow-up logged for Rajesh Deshmukh for ₹3,20,000 overdue balance.",
            snapshot_balance_due=320000.0,
            snapshot_interest=inv2_int,
            snapshot_total_claimable=round(320000.0 + inv2_int, 2),
            delivery_status="Logged / Simulated (No Live Messaging Provider Connected)",
            created_at=datetime.utcnow() - timedelta(days=3),
        ),
    ]
    db.add_all(reminders)
    db.commit()

    _populate_timeline_from_existing_records(db)
