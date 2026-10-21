from __future__ import annotations
from datetime import date
from typing import TYPE_CHECKING, Dict, Any, List
import re

if TYPE_CHECKING:
    from ..models import Invoice, Customer

# RBI Bank Rate (6.75% p.a. assumption) -> MSMED Act Section 16 mandates 3x RBI Bank Rate = 20.25% p.a.
RBI_BANK_RATE = 0.0675
MSMED_ANNUAL_INTEREST_RATE = RBI_BANK_RATE * 3  # 0.2025 (20.25% per annum)

# Configurable Deterministic Priority Score Weights (Default max total = 50 + 30 + 20 = 100 points)
DEFAULT_PRIORITY_WEIGHTS: Dict[str, float] = {
    "overdue_max_points": 50,
    "overdue_points_per_day": 1.0,
    "pre_due_window_days": 7,
    "pre_due_points": 12,
    "amount_max_points": 30,
    "amount_reference_cap_inr": 400000.0,
    "followup_max_points": 20,
    "unfollowed_overdue_points": 20,
    "unanswered_reminder_points": 14,
    "partial_payment_reconcile_points": 10,
}

ACTIVE_PRIORITY_WEIGHTS: Dict[str, float] = dict(DEFAULT_PRIORITY_WEIGHTS)


def get_priority_weights() -> Dict[str, float]:
    return dict(ACTIVE_PRIORITY_WEIGHTS)


def update_priority_weights(new_weights: Dict[str, float]) -> Dict[str, float]:
    for k, v in new_weights.items():
        if k in ACTIVE_PRIORITY_WEIGHTS and v is not None:
            if float(v) < 0:
                raise ValueError(f"Weight '{k}' cannot be negative.")
            ACTIVE_PRIORITY_WEIGHTS[k] = float(v)
    return dict(ACTIVE_PRIORITY_WEIGHTS)


def reset_priority_weights() -> Dict[str, float]:
    ACTIVE_PRIORITY_WEIGHTS.clear()
    ACTIVE_PRIORITY_WEIGHTS.update(DEFAULT_PRIORITY_WEIGHTS)
    return dict(ACTIVE_PRIORITY_WEIGHTS)


def format_inr(amount: float) -> str:
    """Formats a float into Indian Rupee numbering format (e.g., ₹1,25,000.00)."""
    is_negative = amount < 0
    amount = abs(round(float(amount), 2))
    integer_part, _, decimal_part = f"{amount:.2f}".partition(".")
    if len(integer_part) > 3:
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        groups.reverse()
        formatted_int = ",".join(groups) + "," + last_three
    else:
        formatted_int = integer_part

    prefix = "-₹" if is_negative else "₹"
    if decimal_part == "00":
        return f"{prefix}{formatted_int}"
    return f"{prefix}{formatted_int}.{decimal_part}"


def calculate_msmed_compound_interest(principal: float, days_overdue: int) -> float:
    """
    Calculates illustrative compound interest with monthly rests under Section 16 of the MSMED Act, 2006.
    Verified statutory rule: 3 times the Bank Rate notified by the RBI, compounded monthly.
    Application assumptions: RBI Bank Rate = 6.75% p.a. (3x = 20.25% p.a.), 30-day monthly rests,
    and simple pro-rata accrual (days / 365) for remaining fractional days.
    """
    if principal <= 0 or days_overdue <= 0:
        return 0.0

    monthly_rate = MSMED_ANNUAL_INTEREST_RATE / 12.0
    full_months = int(days_overdue) // 30
    remaining_days = int(days_overdue) % 30

    compounded_amount = float(principal) * ((1.0 + monthly_rate) ** full_months)
    if remaining_days > 0:
        compounded_amount *= 1.0 + (MSMED_ANNUAL_INTEREST_RATE * (remaining_days / 365.0))

    interest = compounded_amount - float(principal)
    return round(max(0.0, interest), 2)


def compute_invoice_metrics(
    invoice: Invoice,
    customer: Customer,
    reference_date: date | None = None,
    weights: Dict[str, float] | None = None,
) -> dict:
    """
    Computes overdue days, aging bucket (by due date), statutory MSMED compound interest estimate,
    Section 43B(h) threshold flags (by days since issue date vs 15d/45d limit), and a transparent,
    deterministic collection priority score where all displayed factor bullets sum to the exact total score.
    """
    today = reference_date or date.today()
    w = weights or ACTIVE_PRIORITY_WEIGHTS

    total_amount = round(float(invoice.total_amount), 2)
    if total_amount <= 0:
        raise ValueError("Invoice total_amount must be greater than 0.")

    payments_rel = getattr(invoice, "payments", None)
    if payments_rel is not None and len(payments_rel) > 0:
        paid_from_ledger = sum(float(p.amount) for p in payments_rel)
        amount_paid = round(max(float(invoice.amount_paid or 0.0), paid_from_ledger), 2)
        payments_count = len(payments_rel)
    else:
        amount_paid = round(float(invoice.amount_paid or 0.0), 2)
        payments_count = 1 if amount_paid > 0 else 0

    reminders_rel = getattr(invoice, "reminders", None)
    reminders_logged_count = len(reminders_rel) if reminders_rel is not None else 0

    balance_due = round(max(0.0, total_amount - amount_paid), 2)

    days_since_issue = max(0, (today - invoice.issue_date).days)
    statutory_limit_days = 45 if invoice.msme_agreement else 15

    if balance_due <= 0.01:
        balance_due = 0.0
        status = "Paid"
        days_overdue = 0
        days_until_due = 0
    elif today > invoice.due_date:
        status = "Overdue"
        days_overdue = (today - invoice.due_date).days
        days_until_due = 0
    else:
        days_overdue = 0
        days_until_due = (invoice.due_date - today).days
        if amount_paid > 0:
            status = "Partially Paid"
        else:
            status = "Pending"

    # Aging Bucket (strictly based on days past due_date)
    if balance_due == 0.0:
        aging_bucket = "Settled"
    elif days_overdue == 0:
        aging_bucket = "Current (Not Due)"
    elif days_overdue <= 15:
        aging_bucket = "1–15 Days"
    elif days_overdue <= 30:
        aging_bucket = "16–30 Days"
    elif days_overdue <= 45:
        aging_bucket = "31–45 Days"
    else:
        aging_bucket = "45+ Days Overdue"

    # Illustrative Statutory MSMED Act Interest on unpaid balance
    msmed_interest = calculate_msmed_compound_interest(balance_due, days_overdue)
    total_claimable = round(balance_due + msmed_interest, 2)

    # Income Tax Section 43B(h) threshold check:
    # Verified Rule: 15 days (no written agreement) or up to 45 days (written agreement) from acceptance.
    # Application Assumption: issue_date is used as a proxy for acceptance date when GRN date is unavailable.
    section_43bh_at_risk = bool(
        balance_due > 0 and days_overdue > 0 and days_since_issue > statutory_limit_days
    )

    # Transparent, Deterministic Priority Score
    factors: List[str] = []
    if balance_due == 0.0:
        overdue_points = 0
        amount_points = 0
        followup_points = 0
        priority_score = 0
        risk_level = "Low"
        next_action_type = "NONE"
        ai_recommended_action = "Settled — No collection action required"
        explanation_summary = "Score 0/100: Invoice is fully paid (₹0 balance due)."
    else:
        overdue_max = min(100, int(w["overdue_max_points"]))
        amount_max = min(max(0, 100 - overdue_max), int(w["amount_max_points"]))
        followup_max = min(max(0, 100 - overdue_max - amount_max), int(w["followup_max_points"]))
        amount_cap = max(1.0, float(w["amount_reference_cap_inr"]))

        # Component 1: Overdue Severity or Pre-Due Window (0 to overdue_max)
        if days_overdue > 0:
            overdue_points = min(
                overdue_max,
                int(round(days_overdue * float(w["overdue_points_per_day"]))),
            )
            factors.append(f"+{overdue_points}/{overdue_max} pts: {days_overdue} days past due date")
        elif days_until_due <= int(w["pre_due_window_days"]):
            overdue_points = min(overdue_max, int(w["pre_due_points"]))
            factors.append(
                f"+{overdue_points}/{overdue_max} pts: Due within {days_until_due} days (pre-due window)"
            )
        else:
            overdue_points = 0
            factors.append(f"+0/{overdue_max} pts: Not yet due ({days_until_due} days remaining)")

        # Component 2: Outstanding Principal Exposure (0 to amount_max)
        amount_points = min(
            amount_max,
            max(1, int(round((balance_due / amount_cap) * amount_max))),
        )
        factors.append(
            f"+{amount_points}/{amount_max} pts: {format_inr(balance_due)} unpaid principal exposure"
        )

        # Component 3: Follow-Up & Partial Payment Status (0 to followup_max)
        # Allocate sub-factor points strictly within followup_max budget so sub-factors sum to followup_points
        remaining_followup_budget = followup_max
        followup_points = 0

        if days_overdue > 0 and reminders_logged_count == 0:
            raw_pts = int(w["unfollowed_overdue_points"])
            awarded = min(remaining_followup_budget, raw_pts)
            followup_points += awarded
            remaining_followup_budget -= awarded
            cap_note = (
                f" ({raw_pts} raw pts capped at {followup_max}/{followup_max} follow-up category max)"
                if awarded < raw_pts
                else " (follow-up sub-factor)"
            )
            factors.append(
                f"+{awarded}/{followup_max} pts: Overdue with 0 logged reminders{cap_note}"
            )
        elif days_overdue > 0 and reminders_logged_count > 0:
            raw_pts = int(w["unanswered_reminder_points"])
            awarded = min(remaining_followup_budget, raw_pts)
            followup_points += awarded
            remaining_followup_budget -= awarded
            cap_note = (
                f" ({raw_pts} raw pts capped at {followup_max}/{followup_max} follow-up category max)"
                if awarded < raw_pts
                else " (follow-up sub-factor)"
            )
            factors.append(
                f"+{awarded}/{followup_max} pts: {reminders_logged_count} reminder(s) logged, balance still unpaid{cap_note}"
            )

        if amount_paid > 0 and balance_due > 0:
            raw_pts = int(w["partial_payment_reconcile_points"])
            awarded = min(remaining_followup_budget, raw_pts)
            followup_points += awarded
            remaining_followup_budget -= awarded
            cap_note = (
                f" ({raw_pts} raw pts capped at {followup_max}/{followup_max} follow-up category max)"
                if awarded < raw_pts
                else " (follow-up sub-factor)"
            )
            factors.append(
                f"+{awarded}/{followup_max} pts: Partial payment ({format_inr(amount_paid)}) recorded; remaining balance open{cap_note}"
            )

        if followup_points == 0 and not (amount_paid > 0 and balance_due > 0):
            factors.append(f"+0/{followup_max} pts: Within credit period, no follow-up gap")

        # Total score is the deterministic sum of the 3 components (capped at 100 max)
        priority_score = min(100, overdue_points + amount_points + followup_points)
        max_possible_score = min(100, overdue_max + amount_max + followup_max)

        # Determine Priority Level & Next Best Action
        if days_overdue > 45 or priority_score >= 75:
            risk_level = "Critical"
        elif days_overdue > 15 or priority_score >= 50:
            risk_level = "High"
        elif days_overdue > 0 or days_until_due <= int(w["pre_due_window_days"]):
            risk_level = "Medium"
        else:
            risk_level = "Low"

        if days_overdue > 0 and reminders_logged_count > 0:
            next_action_type = "REVIEW_UNANSWERED_REMINDER"
            if amount_paid > 0:
                ai_recommended_action = (
                    f"Reconcile partial payment ({format_inr(amount_paid)} paid) & follow up on "
                    f"{reminders_logged_count} prior reminder(s) for remaining {format_inr(balance_due)}"
                )
            else:
                ai_recommended_action = (
                    f"Review {reminders_logged_count} unanswered reminder(s) & send updated "
                    f"{'Statutory MSME' if days_overdue > 45 else 'Firm'} follow-up"
                )
        elif days_overdue > 0 and amount_paid > 0:
            next_action_type = "RECONCILE_PARTIAL_PAYMENT"
            ai_recommended_action = (
                f"Acknowledge {format_inr(amount_paid)} part-payment & send reminder for "
                f"remaining {format_inr(balance_due)} ({days_overdue}d overdue)"
            )
        elif days_overdue > 45:
            next_action_type = "FOLLOW_UP_OVERDUE"
            ai_recommended_action = (
                "Send Statutory MSME Intimation (Sec 16 interest estimate + Sec 43B(h) reminder)"
            )
        elif days_overdue > 0:
            next_action_type = "FOLLOW_UP_OVERDUE"
            ai_recommended_action = (
                f"Follow up on overdue invoice ({days_overdue}d past due) with updated balance statement"
            )
        elif days_until_due <= int(w["pre_due_window_days"]):
            next_action_type = "SEND_PRE_DUE_REMINDER"
            ai_recommended_action = (
                f"Send polite reminder before due date (due in {days_until_due} days)"
            )
        else:
            next_action_type = "MONITOR_CURRENT"
            ai_recommended_action = f"Monitor — Due in {days_until_due} days (within credit SLA)"

        explanation_summary = (
            f"Rule-based score {priority_score}/{max_possible_score} = "
            f"{overdue_points} (overdue/timing) + {amount_points} (balance exposure) + "
            f"{followup_points} (follow-up/partial status)."
        )

    priority_breakdown = {
        "overdue_points": overdue_points,
        "amount_points": amount_points,
        "followup_points": followup_points,
        "total_score": priority_score,
        "scoring_method": "Deterministic Weighted Rule Engine (Configurable)",
        "explanation_summary": explanation_summary,
        "factors": factors,
    }

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer_id": customer.id,
        "customer_name": customer.name,
        "company_name": customer.company_name,
        "customer_gstin": customer.gstin,
        "customer_udyam": getattr(customer, "udyam_number", None),
        "customer_phone": customer.phone,
        "customer_email": customer.email,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "total_amount": total_amount,
        "amount_paid": amount_paid,
        "balance_due": balance_due,
        "description": invoice.description,
        "msme_agreement": invoice.msme_agreement,
        "status": status,
        "days_overdue": days_overdue,
        "days_until_due": days_until_due,
        "days_since_issue": days_since_issue,
        "statutory_limit_days": statutory_limit_days,
        "aging_bucket": aging_bucket,
        "msmed_interest": msmed_interest,
        "total_claimable": total_claimable,
        "section_43bh_at_risk": section_43bh_at_risk,
        "risk_level": risk_level,
        "priority_score": priority_score,
        "priority_breakdown": priority_breakdown,
        "priority_explanation": explanation_summary,
        "ai_recommended_action": ai_recommended_action,
        "next_action_type": next_action_type,
        "reminders_logged_count": reminders_logged_count,
        "payments_recorded_count": payments_count,
    }


def build_next_action_queue(computed_invoices: List[dict]) -> List[dict]:
    """
    Builds a prioritized Next-Best-Action Queue for small-business owners with
    transparent reasons and recommended communication tone/channel.
    """
    actionable = [
        inv
        for inv in computed_invoices
        if inv["balance_due"] > 0 and inv["next_action_type"] != "MONITOR_CURRENT"
    ]
    actionable.sort(key=lambda x: (-x["priority_score"], -x["days_overdue"], -x["balance_due"]))

    queue = []
    for inv in actionable:
        if inv["days_overdue"] > 45:
            rec_tone = "Statutory MSME"
            rec_channel = "Email"
        elif inv["days_overdue"] > 15:
            rec_tone = "Firm"
            rec_channel = "WhatsApp"
        else:
            rec_tone = "Polite"
            rec_channel = "WhatsApp"

        reasons = "; ".join(inv["priority_breakdown"]["factors"])
        queue.append(
            {
                "invoice_id": inv["id"],
                "invoice_number": inv["invoice_number"],
                "company_name": inv["company_name"],
                "action_type": inv["next_action_type"],
                "action_label": inv["ai_recommended_action"],
                "priority_level": inv["risk_level"],
                "priority_score": inv["priority_score"],
                "balance_due": inv["balance_due"],
                "msmed_interest": inv["msmed_interest"],
                "days_overdue": inv["days_overdue"],
                "days_until_due": inv["days_until_due"],
                "visible_reason": f"{inv['priority_explanation']} [{reasons}]",
                "recommended_tone": rec_tone,
                "recommended_channel": rec_channel,
            }
        )
    return queue


def compute_cashflow_scenarios(computed_invoices: List[dict], horizon_days: int = 30) -> dict:
    """
    Computes deterministic 30-day cash-inflow scenario estimates (Conservative, Baseline, Optimistic)
    with explicit collection assumptions by aging bucket.
    Separates principal inflow from optional interest recovery so principal share % is exact.
    """
    open_invoices = [i for i in computed_invoices if i["balance_due"] > 0]
    settled_count = sum(1 for i in computed_invoices if i["status"] == "Paid")
    total_outstanding = round(sum(i["balance_due"] for i in open_invoices), 2)
    total_interest = round(sum(i["msmed_interest"] for i in open_invoices), 2)

    bucket_totals = {
        "Current (Not Due)": 0.0,
        "1–15 Days": 0.0,
        "16–30 Days": 0.0,
        "31–45 Days": 0.0,
        "45+ Days Overdue": 0.0,
    }
    for inv in open_invoices:
        b = inv["aging_bucket"]
        if b in bucket_totals:
            bucket_totals[b] = round(bucket_totals[b] + inv["balance_due"], 2)

    cons_rates = {
        "Current (Not Due)": 0.85,
        "1–15 Days": 0.50,
        "16–30 Days": 0.25,
        "31–45 Days": 0.15,
        "45+ Days Overdue": 0.00,
    }
    base_rates = {
        "Current (Not Due)": 1.00,
        "1–15 Days": 0.75,
        "16–30 Days": 0.50,
        "31–45 Days": 0.35,
        "45+ Days Overdue": 0.25,
    }
    opt_rates = {
        "Current (Not Due)": 1.00,
        "1–15 Days": 1.00,
        "16–30 Days": 0.85,
        "31–45 Days": 0.75,
        "45+ Days Overdue": 0.60,
    }

    def build_band(name: str, rates: Dict[str, float], interest_share: float, summary: str) -> dict:
        breakdown: Dict[str, float] = {}
        principal_inflow = 0.0
        for bucket, principal in bucket_totals.items():
            amt = round(principal * rates[bucket], 2)
            breakdown[bucket] = amt
            principal_inflow += amt
        principal_inflow = round(principal_inflow, 2)
        interest_inflow = round(total_interest * interest_share, 2) if (interest_share > 0 and total_interest > 0) else 0.0
        if interest_inflow > 0:
            breakdown["Estimated Interest Recovery"] = interest_inflow
        total_inflow = round(principal_inflow + interest_inflow, 2)
        pct = round((principal_inflow / total_outstanding) * 100.0, 1) if total_outstanding > 0 else 0.0
        return {
            "name": name,
            "expected_inflow_30d": total_inflow,
            "expected_principal_inflow_30d": principal_inflow,
            "expected_interest_inflow_30d": interest_inflow,
            "collection_share_of_outstanding_pct": pct,
            "assumptions_summary": summary,
            "bucket_breakdown": breakdown,
        }

    conservative = build_band(
        "Conservative Estimate",
        cons_rates,
        0.0,
        "Assumes 85% of current invoices, 50% of 1–15d overdue, 25% of 16–30d, 15% of 31–45d, and 0% of 45+d overdue principal are collected within 30 days (0% interest recovery).",
    )
    baseline = build_band(
        "Baseline Estimate",
        base_rates,
        0.0,
        "Assumes 100% of current invoices, 75% of 1–15d overdue, 50% of 16–30d, 35% of 31–45d, and 25% of 45+d overdue principal are collected within 30 days after structured follow-ups.",
    )
    optimistic = build_band(
        "Optimistic Estimate",
        opt_rates,
        0.50,
        "Assumes 100% of current & 1–15d overdue, 85% of 16–30d, 75% of 31–45d, 60% of 45+d overdue principal, plus 50% of estimated MSMED Section 16 interest are recovered within 30 days.",
    )

    insufficient_history = settled_count < 10

    return {
        "horizon_days": horizon_days,
        "total_current_outstanding": total_outstanding,
        "total_accrued_interest": total_interest,
        "conservative": conservative,
        "baseline": baseline,
        "optimistic": optimistic,
        "historical_settled_invoices_count": settled_count,
        "insufficient_historical_data": insufficient_history,
        "methodology_disclaimer": (
            f"Transparent Rule-Based Scenario Estimates (Not Guaranteed Collections). "
            f"Currently only {settled_count} settled invoice(s) exist in the ledger (minimum 10+ closed cycles required for customer-level statistical forecasting), "
            f"so inflows are calculated deterministically from aging-bucket recovery assumptions across all {len(open_invoices)} open invoice(s)."
        ),
    }


def generate_reminder_draft(metrics: dict, tone: str, channel: str) -> dict:
    """
    Generates a payment-aware reminder draft synchronized with the latest invoice balance,
    recorded part-payments, illustrative MSMED Act Section 16 interest, and Section 43B(h) context.
    """
    inv_no = metrics["invoice_number"]
    company = metrics["company_name"]
    contact = metrics["customer_name"]
    total_billed_str = format_inr(metrics["total_amount"])
    paid_so_far_str = format_inr(metrics["amount_paid"])
    balance_str = format_inr(metrics["balance_due"])
    interest_str = format_inr(metrics["msmed_interest"])
    total_str = format_inr(metrics["total_claimable"])
    due_str = metrics["due_date"].strftime("%d %b %Y")
    issue_str = metrics["issue_date"].strftime("%d %b %Y")
    days_overdue = metrics["days_overdue"]
    desc = metrics["description"]

    partial_payment_line = (
        f"• *Total Invoice Amount:* {total_billed_str} (Received so far: {paid_so_far_str})\n"
        if metrics["amount_paid"] > 0
        else ""
    )
    partial_payment_email_line = (
        f"- Original Invoice Total: {total_billed_str} (Part-Payment Received: {paid_so_far_str})\n"
        if metrics["amount_paid"] > 0
        else ""
    )

    if tone == "Polite":
        subject = f"Friendly Payment Reminder: Invoice {inv_no} (Balance: {balance_str})"
        if channel == "WhatsApp":
            body = (
                f"Namaste {contact} ji ({company}),\n\n"
                f"Hope business is going well! This is a gentle reminder regarding Invoice *{inv_no}* "
                f"dated {issue_str} for *{desc}*.\n\n"
                f"{partial_payment_line}"
                f"• *Current Principal Balance Due:* {balance_str}\n"
                f"• *Due Date:* {due_str}\n\n"
                f"Kindly share the UTR / payment confirmation once processed via NEFT/RTGS/UPI so we can update our GST & ledger records.\n\n"
                f"Warm regards,\nAccounts Team (via PayTrack AI)"
            )
        else:
            body = (
                f"Dear {contact},\n\n"
                f"Greetings! We value our ongoing business relationship with {company}.\n\n"
                f"We are writing to kindly remind you that Invoice {inv_no} (issued on {issue_str} for {desc}) "
                f"currently has an outstanding principal balance of {balance_str} with a due date of {due_str}.\n\n"
                f"Invoice Summary:\n"
                f"- Invoice Number: {inv_no}\n"
                f"{partial_payment_email_line}"
                f"- Current Principal Outstanding: {balance_str}\n"
                f"- Due Date: {due_str}\n\n"
                f"If payment has already been initiated, please share the NEFT/RTGS/UPI UTR number for reconciliation.\n\n"
                f"Best regards,\nFinance & Accounts Team"
            )
        rationale = (
            f"Preserves buyer relationship while synchronizing the live {balance_str} principal balance "
            f"{'(acknowledging ' + paid_so_far_str + ' already paid) ' if metrics['amount_paid'] > 0 else ''}"
            f"and requesting a UTR reference."
        )

    elif tone == "Firm":
        subject = f"OVERDUE ALERT ({days_overdue} Days): Immediate Payment Requested for Invoice {inv_no} ({balance_str})"
        if channel == "WhatsApp":
            body = (
                f"Dear {contact} ({company}),\n\n"
                f"Our records show that Invoice *{inv_no}* is now *{days_overdue} days overdue* (Due: {due_str}).\n\n"
                f"{partial_payment_line}"
                f"• *Principal Overdue:* {balance_str}\n"
                f"• *Estimated MSME Delayed Interest (20.25% p.a.):* {interest_str}\n"
                f"• *Total Payable (Principal + Estimated Interest):* {total_str}\n\n"
                f"As a registered MSME supplier, timely working capital rotation is critical for us. "
                f"Please release the payment within 48 hours and share the UTR details to avoid further interest accrual.\n\n"
                f"Regards,\nAccounts & Recovery Desk"
            )
        else:
            body = (
                f"Dear {contact} / Accounts Payable at {company},\n\n"
                f"This is an urgent follow-up regarding overdue Tax Invoice {inv_no} dated {issue_str} ({desc}), "
                f"which was due on {due_str} and is now {days_overdue} days past due.\n\n"
                f"Updated Outstanding Statement:\n"
                f"- Invoice No: {inv_no}\n"
                f"{partial_payment_email_line}"
                f"- Principal Balance Due: {balance_str}\n"
                f"- Estimated Interest u/s 16 MSMED Act (@ 20.25% p.a. assumption): {interest_str}\n"
                f"- Total Amount Payable: {total_str}\n\n"
                f"We request you to prioritize this clearance within the next 2 working days and email the remittance advice / UTR number.\n\n"
                f"Sincerely,\nCredit Control & Finance Team"
            )
        rationale = (
            f"Synchronizes with the live {balance_str} remaining balance after part-payments, "
            f"highlights {days_overdue} overdue days, and quantifies {interest_str} in estimated MSMED interest."
        )

    else:  # Statutory MSME
        subject = f"STATUTORY INTIMATION (MSMED Act Sec 15/16 & Income Tax Sec 43B(h)): Invoice {inv_no} ({total_str})"
        body = (
            f"WITHOUT PREJUDICE (COMMERCIAL FOLLOW-UP INTIMATION — NOT FORMAL LEGAL ADVICE)\n"
            f"To: The Directors / Finance Head, {company} (GSTIN: {metrics['customer_gstin']})\n"
            f"Attn: {contact}\n\n"
            f"Sub: Intimation Regarding Delayed Payment of MSME Dues — Invoice {inv_no}\n\n"
            f"Dear Sir/Madam,\n\n"
            f"1. We supplied goods/services under Tax Invoice {inv_no} dated {issue_str} ({desc}), "
            f"which fell due on {due_str} and remains unpaid for {days_overdue} days past the due date.\n\n"
            f"2. Under Section 15 of the Micro, Small and Medium Enterprises Development (MSMED) Act, 2006, "
            f"buyers are required to clear registered Micro/Small supplier dues within the agreed period (not exceeding 45 days from acceptance, "
            f"or 15 days where no written agreement exists; configured credit limit for this invoice: {metrics['statutory_limit_days']} days).\n\n"
            f"3. Under Section 16 of the MSMED Act, 2006, compound interest with monthly rests at 3 times the RBI Bank Rate "
            f"(estimated at 20.25% p.a. based on a 6.75% RBI Bank Rate assumption) is applicable on overdue balances:\n"
            f"{'   • Original Invoice Amount: ' + total_billed_str + ' (Less Part-Payments: ' + paid_so_far_str + ')\\n' if metrics['amount_paid'] > 0 else ''}"
            f"   • Current Principal Outstanding: {balance_str}\n"
            f"   • Estimated Compound Interest Accrued (from due date): {interest_str}\n"
            f"   • Total Estimated Claimable Amount: {total_str}\n\n"
            f"4. Please also note that under Section 43B(h) of the Income Tax Act, 1961, sums payable to registered Micro/Small "
            f"enterprises beyond the Section 15 time limit are allowable as business expense deductions only in the year of actual payment.\n\n"
            f"We request settlement of {total_str} within 7 days and sharing of the UTR reference so both parties can close this ledger item amicably.\n\n"
            f"Authorized Signatory,\nFinance & Compliance Desk"
        )
        rationale = (
            f"References verified statutory provisions (MSMED Act Sec 15/16 & Income Tax Act Sec 43B(h)) while clearly labeling "
            f"{interest_str} as an estimate based on the 6.75% RBI Bank Rate assumption."
        )

    return {
        "invoice_id": metrics["id"],
        "invoice_number": inv_no,
        "company_name": company,
        "contact_name": contact,
        "channel": channel,
        "tone": tone,
        "subject": subject,
        "message_body": body,
        "balance_due": metrics["balance_due"],
        "msmed_interest": metrics["msmed_interest"],
        "total_claimable": metrics["total_claimable"],
        "days_overdue": days_overdue,
        "ai_rationale": rationale,
        "delivery_status": "Drafted (Not Sent — Manual Review Required)",
    }
