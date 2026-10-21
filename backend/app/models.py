from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    company_name = Column(String(180), nullable=False)
    gstin = Column(String(20), nullable=False)
    udyam_number = Column(String(30), nullable=True)
    email = Column(String(150), nullable=False)
    phone = Column(String(20), nullable=False)
    city = Column(String(80), nullable=False)
    credit_period_days = Column(Integer, default=30)
    reliability_score = Column(Integer, default=80)  # Legacy column retained for DB compatibility
    created_at = Column(DateTime, default=datetime.utcnow)

    invoices = relationship("Invoice", back_populates="customer", cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    total_amount = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0.0)
    description = Column(String(255), nullable=False)
    msme_agreement = Column(Boolean, default=True)  # True = max 45 days; False = max 15 days
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    reminders = relationship("ReminderLog", back_populates="invoice", cascade="all, delete-orphan")
    timeline_events = relationship(
        "InvoiceTimelineEvent", back_populates="invoice", cascade="all, delete-orphan"
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_date = Column(Date, nullable=False)
    payment_mode = Column(String(50), default="NEFT")  # UPI, NEFT, RTGS, Cheque
    reference_number = Column(String(80), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    invoice = relationship("Invoice", back_populates="payments")


class ReminderLog(Base):
    __tablename__ = "reminder_logs"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    channel = Column(String(40), nullable=False)  # WhatsApp, Email, Demand Notice
    tone = Column(String(40), nullable=False)     # Polite, Firm, Statutory MSME
    subject = Column(String(200), nullable=False)
    message_body = Column(Text, nullable=False)
    # Immutable historical snapshot at the moment the reminder was logged
    snapshot_balance_due = Column(Float, nullable=True)
    snapshot_interest = Column(Float, nullable=True)
    snapshot_total_claimable = Column(Float, nullable=True)
    delivery_status = Column(
        String(80),
        default="Logged / Simulated (No Live Messaging Provider Connected)",
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    invoice = relationship("Invoice", back_populates="reminders")


class InvoiceTimelineEvent(Base):
    __tablename__ = "invoice_timeline_events"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    event_type = Column(
        String(50), nullable=False
    )  # INVOICE_CREATED, PAYMENT_RECEIVED, BALANCE_UPDATED, REMINDER_DRAFTED, REMINDER_EDITED, REMINDER_LOGGED
    title = Column(String(160), nullable=False)
    details = Column(Text, nullable=False)
    amount = Column(Float, nullable=True)
    balance_after = Column(Float, nullable=True)
    interest_snapshot = Column(Float, nullable=True)
    delivery_status = Column(
        String(80), nullable=True
    )  # Drafted | Draft Edited | Logged / Simulated | Verified Recorded
    created_at = Column(DateTime, default=datetime.utcnow)

    invoice = relationship("Invoice", back_populates="timeline_events")
