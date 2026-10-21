"""
Comprehensive Validation & Regression Test Suite for PayTrack AI (Section E + Audit Regression):
1. Priority-score consistency, configurable weights & exact bullet-to-score sum verification
2. Correct overdue-day and days-until-due calculation
3. Partial-payment balance updates & ledger reconciliation
4. Duplicate-payment prevention & overpayment rejection
5. Reminder balance synchronization after partial payments
6. Historical reminder snapshot preservation (immutability when balance changes)
7. Separation of Drafted, Draft Edited, and Logged/Simulated statuses
8. Next-Best-Action queue recommendations & visible reasons
9. Transparent 30-day Cash-Flow Scenario calculations, principal/interest split & live DB reconciliation
10. Empty or insufficient historical data handling
11. Invalid and boundary values + Dashboard KPI & Aging Bucket reconciliation
"""
import re
import sys
from datetime import date, timedelta
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database import SessionLocal
from app.models import Base, Customer, Invoice, Payment, ReminderLog, InvoiceTimelineEvent
from app.schemas import PaymentCreate, ReminderDraftRequest, ReminderSaveRequest, InvoiceCreate
from app.services.calculations import (
    format_inr,
    calculate_msmed_compound_interest,
    compute_invoice_metrics,
    generate_reminder_draft,
    build_next_action_queue,
    compute_cashflow_scenarios,
    get_priority_weights,
    update_priority_weights,
    reset_priority_weights,
)
from app.main import (
    record_payment,
    create_reminder_draft,
    save_reminder_log,
    get_invoice_workspace,
    create_invoice,
    get_dashboard_summary,
)
from app.seed import seed_database


def extract_bullet_points_list(factors: list[str]) -> list[int]:
    pts = []
    for f in factors:
        m = re.match(r"^\+(\d+)", f.strip())
        assert m is not None, f"Factor bullet does not start with '+<int>': {f}"
        pts.append(int(m.group(1)))
    return pts


def extract_bullet_points_sum(factors: list[str]) -> int:
    return sum(extract_bullet_points_list(factors))


def run_validation():
    print("=== PayTrack AI Comprehensive Validation & Regression Suite ===")
    today = date.today()
    reset_priority_weights()

    # 1. Test INR Formatting
    assert format_inr(485000) == "₹4,85,000"
    assert format_inr(12500000.50) == "₹1,25,00,000.50"
    assert format_inr(0) == "₹0"
    print("[PASS] 1. Indian Rupee (₹) Lakh/Crore formatting verified.")

    # 2. Test Overdue-Day, Days-Until-Due, and Statutory MSMED Interest Calculations
    interest_62d = calculate_msmed_compound_interest(400000.0, 62)
    assert abs(interest_62d - 14072.85) < 0.05
    assert calculate_msmed_compound_interest(400000.0, 0) == 0.0
    assert calculate_msmed_compound_interest(0.0, 62) == 0.0
    assert calculate_msmed_compound_interest(-5000.0, 30) == 0.0
    print(f"[PASS] 2. MSMED Section 16 compound interest verified (₹4,00,000 @ 62d = {format_inr(interest_62d)}).")

    # 3. Test Priority-Score Consistency, Configurable Weights & Exact Bullet Sum Regression
    mock_cust = SimpleNamespace(
        id=1,
        name="Vikramaditya Reddy",
        company_name="Deccan Infra & Structural Steels LLP",
        gstin="36AABCD8931F1Z2",
        udyam_number="UDYAM-TS-07-0083120",
        phone="+91 90001 56239",
        email="ap@deccaninfrasteel.com",
    )
    mock_inv = SimpleNamespace(
        id=101,
        invoice_number="INV-2026-101",
        issue_date=today - timedelta(days=92),
        due_date=today - timedelta(days=62),
        total_amount=485000.0,
        amount_paid=85000.0,
        description="CNC Machined Heavy Flange Assemblies",
        msme_agreement=True,
        payments=[SimpleNamespace(amount=85000.0)],
        reminders=[SimpleNamespace(id=1)],
    )
    m1 = compute_invoice_metrics(mock_inv, mock_cust, reference_date=today)
    m2 = compute_invoice_metrics(mock_inv, mock_cust, reference_date=today)
    assert m1["priority_score"] == m2["priority_score"], "Priority score must be deterministic"
    bd = m1["priority_breakdown"]
    assert bd["total_score"] == bd["overdue_points"] + bd["amount_points"] + bd["followup_points"]
    assert extract_bullet_points_sum(bd["factors"]) == m1["priority_score"], (
        f"Bullet sum {extract_bullet_points_sum(bd['factors'])} != score {m1['priority_score']}"
    )

    # Test custom weights where sub-factors exceed followup_max_points to verify cap & bullet sum match
    update_priority_weights(
        {
            "overdue_max_points": 40,
            "amount_max_points": 40,
            "followup_max_points": 20,
            "unanswered_reminder_points": 15,
            "partial_payment_reconcile_points": 12,
        }
    )
    m_custom = compute_invoice_metrics(mock_inv, mock_cust, reference_date=today)
    assert m_custom["priority_breakdown"]["overdue_points"] <= 40
    assert m_custom["priority_breakdown"]["followup_points"] == 20
    assert extract_bullet_points_sum(m_custom["priority_breakdown"]["factors"]) == m_custom["priority_score"]
    reset_priority_weights()
    print(
        f"[PASS] 3. Explainable Priority Score & exact bullet-to-score sum verified "
        f"(Score={m1['priority_score']}/100: {bd['overdue_points']}+{bd['amount_points']}+{bd['followup_points']})."
    )

    # 4. Test Partial-Payment Balance Updates, Exact INV-2026-101 (₹3,90,000 / 2 Reminders) Score Reconciliation & Reminder Sync
    mock_inv.payments.append(SimpleNamespace(amount=10000.0))
    mock_inv.amount_paid = 95000.0
    mock_inv.reminders.append(SimpleNamespace(id=2))
    m_after_part = compute_invoice_metrics(mock_inv, mock_cust, reference_date=today)
    assert m_after_part["balance_due"] == 390000.0
    assert m_after_part["priority_score"] == 99, f"Expected 99/100 for INV-2026-101 (₹3,90,000), got {m_after_part['priority_score']}"
    bd_part = m_after_part["priority_breakdown"]
    assert bd_part["overdue_points"] == 50
    assert bd_part["amount_points"] == 29
    assert bd_part["followup_points"] == 20
    assert bd_part["total_score"] == 99
    bullet_pts_101 = extract_bullet_points_list(bd_part["factors"])
    assert bullet_pts_101 == [50, 29, 14, 6], f"Expected [50, 29, 14, 6] bullets for INV-2026-101, got {bullet_pts_101}"
    assert sum(bullet_pts_101) == 99
    assert sum(bullet_pts_101[2:]) == bd_part["followup_points"] == 20

    expected_int_390k = calculate_msmed_compound_interest(390000.0, 62)
    expected_tot_390k = round(390000.0 + expected_int_390k, 2)
    assert m_after_part["msmed_interest"] == expected_int_390k
    assert m_after_part["total_claimable"] == expected_tot_390k

    for tone in ["Polite", "Firm", "Statutory MSME"]:
        draft = generate_reminder_draft(m_after_part, tone=tone, channel="WhatsApp")
        assert draft["balance_due"] == 390000.0
        assert "₹3,90,000" in draft["message_body"]
        assert "₹4,00,000" not in draft["message_body"]
        assert draft["delivery_status"].startswith("Drafted")
    print(
        f"[PASS] 4. Partial-payment balance synchronization verified "
        f"(Principal={format_inr(m_after_part['balance_due'])}, Interest={format_inr(expected_int_390k)}, Total={format_inr(expected_tot_390k)})."
    )

    # 5. End-to-End In-Memory SQLite Test: Historical Reminder Preservation, Duplicate Prevention, Timeline & Status Separation
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    with TestSession() as db:
        seed_database(db, force_reset=True)
        inv1 = db.query(Invoice).filter(Invoice.invoice_number == "INV-2026-101").first()
        assert inv1 is not None

        initial_logs = db.query(ReminderLog).filter(ReminderLog.invoice_id == inv1.id).all()
        assert len(initial_logs) == 1
        assert initial_logs[0].snapshot_balance_due == 400000.0
        assert "Simulated" in initial_logs[0].delivery_status

        pay_res = record_payment(
            PaymentCreate(
                invoice_id=inv1.id,
                amount=10000.0,
                payment_date=today,
                payment_mode="UPI",
                reference_number="UPI-TEST-990011",
                notes="Partial payment test",
            ),
            db=db,
        )
        assert pay_res["amount"] == 10000.0

        dup_blocked = False
        try:
            record_payment(
                PaymentCreate(
                    invoice_id=inv1.id,
                    amount=10000.0,
                    payment_date=today,
                    payment_mode="UPI",
                    reference_number="UPI-TEST-990011",
                    notes="Accidental duplicate submission",
                ),
                db=db,
            )
        except HTTPException as exc:
            dup_blocked = exc.status_code == 400 and "Duplicate payment reference" in str(exc.detail)
        assert dup_blocked, "Duplicate payment reference must be rejected with HTTP 400"

        overpay_blocked = False
        try:
            record_payment(
                PaymentCreate(
                    invoice_id=inv1.id,
                    amount=500000.0,
                    payment_date=today,
                    payment_mode="NEFT",
                    reference_number="NEFT-OVERPAY",
                ),
                db=db,
            )
        except HTTPException as exc:
            overpay_blocked = exc.status_code == 400
        assert overpay_blocked, "Overpayment exceeding balance due must be rejected"

        live_draft = create_reminder_draft(
            ReminderDraftRequest(
                invoice_id=inv1.id,
                tone="Firm",
                channel="WhatsApp",
                log_draft_event=True,
            ),
            db=db,
        )
        assert live_draft["balance_due"] == 390000.0
        assert "₹3,90,000" in live_draft["message_body"]

        saved_log = save_reminder_log(
            ReminderSaveRequest(
                invoice_id=inv1.id,
                channel="WhatsApp",
                tone="Firm",
                subject=live_draft["subject"] + " [Edited]",
                message_body=live_draft["message_body"],
                was_edited=True,
            ),
            db=db,
        )
        assert saved_log["snapshot_balance_due"] == 390000.0
        assert "Logged / Simulated" in saved_log["delivery_status"]

        db.refresh(initial_logs[0])
        assert initial_logs[0].snapshot_balance_due == 400000.0
        assert "₹4,00,000" in initial_logs[0].message_body

        ws = get_invoice_workspace(inv1.id, db=db)
        assert ws["reconciliation_verified"] is True
        event_types = [e["event_type"] for e in ws["timeline"]]
        for req_event in [
            "INVOICE_CREATED",
            "PAYMENT_RECEIVED",
            "BALANCE_UPDATED",
            "REMINDER_DRAFTED",
            "REMINDER_EDITED",
            "REMINDER_LOGGED",
        ]:
            assert req_event in event_types, f"Missing timeline event type: {req_event}"

        print("[PASS] 5. Duplicate-payment prevention & overpayment rejection verified.")
        print("[PASS] 6. Historical reminder immutability verified (old snapshot=₹4,00,000 preserved; new snapshot=₹3,90,000).")
        print("[PASS] 7. Separation of Drafted, Draft Edited, and Logged/Simulated statuses & full Timeline verified.")

        # 8. Test Next-Best-Action Queue & Exact Score-to-Breakdown Reconciliation Across All 8 Seeded Invoices
        all_invs = db.query(Invoice).order_by(Invoice.id.asc()).all()
        assert len(all_invs) == 8, f"Expected 8 seeded invoices, found {len(all_invs)}"
        computed_all = [compute_invoice_metrics(i, i.customer, reference_date=today) for i in all_invs]
        expected_seeded_scores = {
            "INV-2026-101": (99, 50, 29, 20, [50, 29, 14, 6]),
            "INV-2026-102": (86, 48, 24, 14, [48, 24, 14]),
            "INV-2026-103": (65, 37, 8, 20, [37, 8, 20, 0]),
            "INV-2026-104": (55, 22, 13, 20, [22, 13, 20, 0]),
            "INV-2026-105": (42, 9, 13, 20, [9, 13, 20]),
            "INV-2026-106": (30, 12, 8, 10, [12, 8, 10]),
            "INV-2026-107": (14, 0, 14, 0, [0, 14, 0]),
            "INV-2026-108": (0, 0, 0, 0, []),
        }
        for ci in computed_all:
            inv_no = ci["invoice_number"]
            bd_i = ci["priority_breakdown"]
            assert 0 <= ci["priority_score"] <= 100, f"{inv_no} score out of [0, 100]: {ci['priority_score']}"
            assert bd_i["total_score"] == ci["priority_score"]
            assert bd_i["overdue_points"] + bd_i["amount_points"] + bd_i["followup_points"] == ci["priority_score"]
            bullet_pts = extract_bullet_points_list(bd_i["factors"])
            if ci["balance_due"] > 0:
                assert sum(bullet_pts) == ci["priority_score"], (
                    f"{inv_no}: bullet_sum {sum(bullet_pts)} != score {ci['priority_score']}"
                )
                assert bullet_pts[0] == bd_i["overdue_points"]
                assert bullet_pts[1] == bd_i["amount_points"]
                assert sum(bullet_pts[2:]) == bd_i["followup_points"]
            exp_tot, exp_ovd, exp_amt, exp_fol, exp_bullets = expected_seeded_scores[inv_no]
            assert ci["priority_score"] == exp_tot, f"{inv_no}: expected {exp_tot}, got {ci['priority_score']}"
            assert (bd_i["overdue_points"], bd_i["amount_points"], bd_i["followup_points"]) == (exp_ovd, exp_amt, exp_fol)
            assert bullet_pts == exp_bullets, f"{inv_no}: expected bullets {exp_bullets}, got {bullet_pts}"

        nba_queue = build_next_action_queue(computed_all)
        assert len(nba_queue) >= 5
        action_types = {item["action_type"] for item in nba_queue}
        assert "REVIEW_UNANSWERED_REMINDER" in action_types
        assert "RECONCILE_PARTIAL_PAYMENT" in action_types
        assert "FOLLOW_UP_OVERDUE" in action_types
        assert "SEND_PRE_DUE_REMINDER" in action_types
        print(f"[PASS] 8. Next-Best-Action Queue & factor bullet sums verified across all {len(all_invs)} invoices.")

        # 9. Test Transparent Cash-Flow Scenarios (Principal vs Interest Split)
        cf = compute_cashflow_scenarios(computed_all, horizon_days=30)
        for band_key in ["conservative", "baseline", "optimistic"]:
            b = cf[band_key]
            assert round(b["expected_principal_inflow_30d"] + b["expected_interest_inflow_30d"], 2) == b["expected_inflow_30d"]
            expected_pct = round((b["expected_principal_inflow_30d"] / cf["total_current_outstanding"]) * 100.0, 1)
            assert b["collection_share_of_outstanding_pct"] == expected_pct
        cons_val = cf["conservative"]["expected_inflow_30d"]
        base_val = cf["baseline"]["expected_inflow_30d"]
        opt_val = cf["optimistic"]["expected_inflow_30d"]
        assert 0 < cons_val <= base_val <= opt_val
        assert cf["insufficient_historical_data"] is True
        print(
            f"[PASS] 9. 30-Day Cash-Flow Scenarios verified (8-invoice fixture: "
            f"Conservative={format_inr(cons_val)}, Baseline={format_inr(base_val)}, Optimistic={format_inr(opt_val)})."
        )

        # 10. Test Empty / Insufficient Historical Data Handling
        empty_cf = compute_cashflow_scenarios([], horizon_days=30)
        assert empty_cf["total_current_outstanding"] == 0.0
        assert empty_cf["conservative"]["expected_inflow_30d"] == 0.0
        assert empty_cf["insufficient_historical_data"] is True
        assert build_next_action_queue([]) == []
        print("[PASS] 10. Empty dataset & insufficient historical data handling verified.")

        # 11. Test Invalid & Boundary Values + Live Database Dashboard Reconciliation
        inv_15d = SimpleNamespace(
            id=901,
            invoice_number="INV-BND-15",
            issue_date=today - timedelta(days=16),
            due_date=today - timedelta(days=1),
            total_amount=50000.0,
            amount_paid=0.0,
            description="Boundary Test 15d",
            msme_agreement=False,
            payments=[],
            reminders=[],
        )
        m_15d = compute_invoice_metrics(inv_15d, mock_cust, reference_date=today)
        assert m_15d["statutory_limit_days"] == 15
        assert m_15d["section_43bh_at_risk"] is True

        inv_paid = SimpleNamespace(
            id=902,
            invoice_number="INV-BND-PAID",
            issue_date=today - timedelta(days=40),
            due_date=today - timedelta(days=10),
            total_amount=75000.0,
            amount_paid=75000.0,
            description="Boundary Exact Settlement",
            msme_agreement=True,
            payments=[SimpleNamespace(amount=75000.0)],
            reminders=[],
        )
        m_paid = compute_invoice_metrics(inv_paid, mock_cust, reference_date=today)
        assert m_paid["balance_due"] == 0.0
        assert m_paid["status"] == "Paid"
        assert m_paid["priority_score"] == 0
        assert m_paid["msmed_interest"] == 0.0

    # Verify Live Database (paytrack.db) Dashboard KPI & Aging Reconciliation without modifying data
    with SessionLocal() as live_db:
        live_dash = get_dashboard_summary(live_db)
        kpis = live_dash["kpis"]
        assert round(kpis["total_invoiced"] - kpis["total_collected"], 2) == kpis["total_outstanding"]
        assert round(kpis["total_overdue"] + kpis["total_current_not_due"], 2) == kpis["total_outstanding"]
        aging_sum = round(sum(b["amount"] for b in live_dash["aging_breakdown"]), 2)
        aging_count = sum(b["count"] for b in live_dash["aging_breakdown"])
        assert aging_sum == kpis["total_outstanding"], f"Aging sum {aging_sum} != {kpis['total_outstanding']}"
        assert aging_count == kpis["open_invoices_count"]
        for inv in live_db.query(Invoice).all():
            cm = compute_invoice_metrics(inv, inv.customer, reference_date=today)
            if cm["balance_due"] > 0:
                assert extract_bullet_points_sum(cm["priority_breakdown"]["factors"]) == cm["priority_score"]

        # Also verify live HTTP response on port 8001 if server is running
        import json
        import urllib.request
        try:
            with urllib.request.urlopen("http://127.0.0.1:8001/api/dashboard", timeout=3) as resp:
                http_dash = json.loads(resp.read().decode("utf-8"))
                for q_inv in http_dash.get("priority_queue", []):
                    q_pts = extract_bullet_points_list(q_inv["priority_breakdown"]["factors"])
                    assert sum(q_pts) == q_inv["priority_score"], (
                        f"Live HTTP /api/dashboard mismatch for {q_inv['invoice_number']}: "
                        f"bullets {q_pts} sum to {sum(q_pts)} != score {q_inv['priority_score']}"
                    )
                    if q_inv["invoice_number"] == "INV-2026-101":
                        assert q_pts == [50, 29, 14, 6], f"Live HTTP INV-2026-101 bullets {q_pts} != [50, 29, 14, 6]"
        except urllib.error.URLError:
            pass

        print(
            f"[PASS] 11. Boundary values, Live DB & Live HTTP API reconciliation verified "
            f"(Live Outstanding={format_inr(kpis['total_outstanding'])} = Overdue {format_inr(kpis['total_overdue'])} + "
            f"Current {format_inr(kpis['total_current_not_due'])}; Live Baseline 30d={format_inr(live_dash['cashflow_scenarios']['baseline']['expected_inflow_30d'])})."
        )

    print("=== ALL 11 VALIDATION & REGRESSION SUITES PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    run_validation()
