import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard,
  FileText,
  Users,
  IndianRupee,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Plus,
  Copy,
  Send,
  RefreshCw,
  ShieldAlert,
  ArrowUpRight,
  Building2,
  Sliders,
  History,
  TrendingUp,
  Info,
  FolderCheck,
} from 'lucide-react';
import { api, formatINR } from './api';
import {
  Customer,
  Invoice,
  Payment,
  DashboardSummary,
  ReminderDraft,
  ReminderLog,
  InvoiceWorkspace,
  PriorityWeightsConfig,
} from './types';

type TabKey = 'dashboard' | 'invoices' | 'customers' | 'payments' | 'reminders';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard');
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [reminders, setReminders] = useState<ReminderLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Filter state for Invoices
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Modals
  const [showInvoiceModal, setShowInvoiceModal] = useState(false);
  const [showCustomerModal, setShowCustomerModal] = useState(false);
  const [showWeightsModal, setShowWeightsModal] = useState(false);
  const [paymentModalInvoice, setPaymentModalInvoice] = useState<Invoice | null>(null);
  const [workspaceData, setWorkspaceData] = useState<InvoiceWorkspace | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState<boolean>(false);

  // Priority Weights State
  const [weightsForm, setWeightsForm] = useState<PriorityWeightsConfig>({
    overdue_max_points: 50,
    overdue_points_per_day: 1.0,
    pre_due_window_days: 7,
    pre_due_points: 12,
    amount_max_points: 30,
    amount_reference_cap_inr: 400000,
    followup_max_points: 20,
    unfollowed_overdue_points: 20,
    unanswered_reminder_points: 14,
    partial_payment_reconcile_points: 10,
  });

  // Reminder Generator state
  const [selectedReminderInvoiceId, setSelectedReminderInvoiceId] = useState<number>(0);
  const [reminderTone, setReminderTone] = useState<string>('Firm');
  const [reminderChannel, setReminderChannel] = useState<string>('WhatsApp');
  const [currentDraft, setCurrentDraft] = useState<ReminderDraft | null>(null);
  const [draftWasEdited, setDraftWasEdited] = useState<boolean>(false);
  const [draftLoading, setDraftLoading] = useState<boolean>(false);

  // Local calendar date helper (avoids UTC date-shift in IST)
  const formatLocalDate = (d: Date) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  // New Invoice Form State
  const todayStr = formatLocalDate(new Date());
  const defaultDueStr = formatLocalDate(new Date(Date.now() + 30 * 86400000));
  const [invForm, setInvForm] = useState({
    invoice_number: `INV-2026-${Math.floor(109 + Math.random() * 800)}`,
    customer_id: 1,
    issue_date: todayStr,
    due_date: defaultDueStr,
    total_amount: '',
    description: '',
    msme_agreement: true,
  });

  // New Customer Form State
  const [custForm, setCustForm] = useState({
    name: '',
    company_name: '',
    gstin: '',
    udyam_number: '',
    email: '',
    phone: '',
    city: '',
    credit_period_days: 30,
  });

  // Payment Form State
  const [payForm, setPayForm] = useState({
    amount: '',
    payment_date: todayStr,
    payment_mode: 'NEFT',
    reference_number: '',
    notes: '',
  });

  const showToastMsg = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const loadAllData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashData, invData, custData, payData, remData] = await Promise.all([
        api.getDashboard(),
        api.getInvoices(),
        api.getCustomers(),
        api.getPayments(),
        api.getReminders(),
      ]);
      setDashboard(dashData);
      setInvoices(invData);
      setCustomers(custData);
      setPayments(payData);
      setReminders(remData);
      if (dashData.priority_weights) {
        setWeightsForm(dashData.priority_weights);
      }

      const unpaid = invData.filter((i) => i.balance_due > 0);
      setSelectedReminderInvoiceId((prevId) => {
        if (unpaid.length === 0) return 0;
        const stillUnpaid = unpaid.some((i) => i.id === prevId);
        return stillUnpaid ? prevId : unpaid[0].id;
      });
    } catch (err: any) {
      setError(
        err.message ||
          'Could not connect to FastAPI backend at http://127.0.0.1:8001. Please start the backend server.'
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, []);

  const selectedReminderInvoice = invoices.find((i) => i.id === selectedReminderInvoiceId);

  // Auto-generate draft when reminder tab, selected invoice, tone/channel, or invoice balance/payments change
  useEffect(() => {
    if (selectedReminderInvoiceId > 0) {
      handleGenerateDraft(selectedReminderInvoiceId, reminderTone, reminderChannel, false);
    } else {
      setCurrentDraft(null);
    }
  }, [
    selectedReminderInvoiceId,
    reminderTone,
    reminderChannel,
    selectedReminderInvoice?.balance_due,
    selectedReminderInvoice?.amount_paid,
    payments.length,
  ]);

  const handleGenerateDraft = async (
    invId: number,
    tone: string,
    channel: string,
    logEvent: boolean = false
  ) => {
    if (!invId) return;
    setDraftLoading(true);
    setDraftWasEdited(false);
    try {
      const draft = await api.generateReminderDraft({
        invoice_id: invId,
        tone,
        channel,
        log_draft_event: logEvent,
      });
      setCurrentDraft(draft);
    } catch (err: any) {
      showToastMsg(err.message || 'Failed to generate draft');
    } finally {
      setDraftLoading(false);
    }
  };

  const openReminderForInvoice = (inv: Invoice, preferredTone?: string, preferredChannel?: string) => {
    let nextTone = preferredTone || 'Polite';
    let nextChannel = preferredChannel || 'WhatsApp';
    if (!preferredTone) {
      if (inv.days_overdue > 45) {
        nextTone = 'Statutory MSME';
        nextChannel = 'Email';
      } else if (inv.days_overdue > 15) {
        nextTone = 'Firm';
        nextChannel = 'WhatsApp';
      }
    }
    setSelectedReminderInvoiceId(inv.id);
    setReminderTone(nextTone);
    setReminderChannel(nextChannel);
    setActiveTab('reminders');
    handleGenerateDraft(inv.id, nextTone, nextChannel, true);
  };

  const openWorkspaceModal = async (invoiceId: number) => {
    setWorkspaceLoading(true);
    try {
      const ws = await api.getInvoiceWorkspace(invoiceId);
      setWorkspaceData(ws);
    } catch (err: any) {
      showToastMsg(err.message || 'Could not load invoice workspace');
    } finally {
      setWorkspaceLoading(false);
    }
  };

  const openPaymentModal = (inv: Invoice) => {
    setPaymentModalInvoice(inv);
    setPayForm({
      amount: String(inv.balance_due),
      payment_date: todayStr,
      payment_mode: 'NEFT',
      reference_number: `UTR${Math.floor(100000000 + Math.random() * 900000000)}`,
      notes: `Settlement towards ${inv.invoice_number}`,
    });
  };

  const handleSavePriorityWeights = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.updatePriorityWeights(weightsForm);
      setShowWeightsModal(false);
      showToastMsg('Deterministic priority score weights updated & queue recalculated!');
      await loadAllData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleResetPriorityWeights = async () => {
    try {
      const res = await api.resetPriorityWeights();
      setWeightsForm(res.weights);
      showToastMsg('Priority weights restored to default configuration.');
      await loadAllData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleCreateInvoice = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createInvoice({
        invoice_number: invForm.invoice_number,
        customer_id: Number(invForm.customer_id),
        issue_date: invForm.issue_date,
        due_date: invForm.due_date,
        total_amount: Number(invForm.total_amount),
        description: invForm.description,
        msme_agreement: invForm.msme_agreement,
      });
      setShowInvoiceModal(false);
      showToastMsg(`Invoice ${invForm.invoice_number} created & logged in timeline!`);
      setInvForm({
        ...invForm,
        invoice_number: `INV-2026-${Math.floor(109 + Math.random() * 800)}`,
        total_amount: '',
        description: '',
      });
      await loadAllData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleCreateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createCustomer({
        ...custForm,
        credit_period_days: Number(custForm.credit_period_days),
      });
      setShowCustomerModal(false);
      showToastMsg(`Customer ${custForm.company_name} added!`);
      setCustForm({
        name: '',
        company_name: '',
        gstin: '',
        udyam_number: '',
        email: '',
        phone: '',
        city: '',
        credit_period_days: 30,
      });
      await loadAllData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleRecordPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!paymentModalInvoice) return;
    try {
      await api.recordPayment({
        invoice_id: paymentModalInvoice.id,
        amount: Number(payForm.amount),
        payment_date: payForm.payment_date,
        payment_mode: payForm.payment_mode,
        reference_number: payForm.reference_number,
        notes: payForm.notes,
      });
      const recInvId = paymentModalInvoice.id;
      showToastMsg(
        `Recorded ${formatINR(Number(payForm.amount))} for ${paymentModalInvoice.invoice_number} — balance, interest & reminder draft synchronized!`
      );
      setPaymentModalInvoice(null);
      await loadAllData();
      if (workspaceData && workspaceData.invoice.id === recInvId) {
        await openWorkspaceModal(recInvId);
      }
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleLogReminder = async () => {
    if (!currentDraft) return;
    try {
      await api.saveReminderLog({
        invoice_id: currentDraft.invoice_id,
        channel: currentDraft.channel,
        tone: currentDraft.tone,
        subject: currentDraft.subject,
        message_body: currentDraft.message_body,
        was_edited: draftWasEdited,
      });
      showToastMsg(
        `Reminder logged with immutable balance snapshot (${formatINR(currentDraft.balance_due)})!`
      );
      setDraftWasEdited(false);
      await loadAllData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleResetDemo = async () => {
    await api.resetDemo();
    showToastMsg('Demo dataset & timeline reset to initial Pitch Fest state!');
    await loadAllData();
  };

  const filteredInvoices = invoices.filter((inv) => {
    if (statusFilter === 'ALL') return true;
    if (statusFilter === '43BH') return inv.section_43bh_at_risk;
    return inv.status.toUpperCase() === statusFilter;
  });

  const renderStatusBadge = (status: Invoice['status']) => {
    if (status === 'Overdue') return <span className="badge badge-overdue">Overdue</span>;
    if (status === 'Paid') return <span className="badge badge-paid">Paid</span>;
    if (status === 'Partially Paid')
      return <span className="badge badge-partial">Partially Paid</span>;
    return <span className="badge badge-pending">Pending</span>;
  };

  const renderPriorityBadge = (level: string, score: number) => {
    const cls =
      level === 'Critical'
        ? 'badge-critical'
        : level === 'High'
        ? 'badge-overdue'
        : level === 'Medium'
        ? 'badge-partial'
        : 'badge-low';
    return (
      <span className={`badge ${cls}`}>
        {level} ({score}/100)
      </span>
    );
  };

  // Ensures displayed factor bullets reconcile 100% with category totals & priority_score (max 100)
  const getReconciledFactors = (inv: Invoice, followupMax: number = 20): { factors: string[]; points: number[] } => {
    const rawFactors = inv.priority_breakdown?.factors || [];
    if (inv.balance_due <= 0 || rawFactors.length === 0) {
      return { factors: rawFactors, points: [] };
    }
    let remainingFollowup = inv.priority_breakdown.followup_points;
    const reconciledFactors: string[] = [];
    const points: number[] = [];

    rawFactors.forEach((f, idx) => {
      const m = f.trim().match(/^\+(\d+)(?:\/(\d+))?\s*pts:\s*(.*)$/);
      if (!m) {
        reconciledFactors.push(f);
        return;
      }
      const rawPts = Number(m[1]);
      const restText = m[3];
      if (idx === 0) {
        const awarded = inv.priority_breakdown.overdue_points;
        points.push(awarded);
        reconciledFactors.push(`+${awarded}/${dashboard?.priority_weights?.overdue_max_points ?? 50} pts: ${restText}`);
      } else if (idx === 1) {
        const awarded = inv.priority_breakdown.amount_points;
        points.push(awarded);
        reconciledFactors.push(`+${awarded}/${dashboard?.priority_weights?.amount_max_points ?? 30} pts: ${restText}`);
      } else {
        const awarded = Math.min(remainingFollowup, rawPts);
        remainingFollowup = Math.max(0, remainingFollowup - awarded);
        points.push(awarded);
        const cleanRest = restText.replace(/\s*\([^)]*follow-up[^)]*\)\s*$/i, '').trim();
        const suffix =
          awarded < rawPts
            ? ` (${rawPts} raw pts capped at ${followupMax}/${followupMax} follow-up category max)`
            : ` (follow-up sub-factor)`;
        reconciledFactors.push(`+${awarded}/${followupMax} pts: ${cleanRest}${suffix}`);
      }
    });

    return { factors: reconciledFactors, points };
  };

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand-box">
          <div className="brand-logo">₹</div>
          <div>
            <div className="brand-title">PayTrack AI</div>
            <div className="brand-sub">Explainable MSME Recovery</div>
          </div>
        </div>

        <nav className="nav-list">
          <button
            className={`nav-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            <LayoutDashboard size={18} />
            Dashboard & Action Queue
          </button>
          <button
            className={`nav-btn ${activeTab === 'invoices' ? 'active' : ''}`}
            onClick={() => setActiveTab('invoices')}
          >
            <FileText size={18} />
            Invoices & Timeline
          </button>
          <button
            className={`nav-btn ${activeTab === 'customers' ? 'active' : ''}`}
            onClick={() => setActiveTab('customers')}
          >
            <Users size={18} />
            Customer Directory
          </button>
          <button
            className={`nav-btn ${activeTab === 'payments' ? 'active' : ''}`}
            onClick={() => setActiveTab('payments')}
          >
            <IndianRupee size={18} />
            Payment Ledger
          </button>
          <button
            className={`nav-btn ${activeTab === 'reminders' ? 'active' : ''}`}
            onClick={() => setActiveTab('reminders')}
          >
            <Sparkles size={18} />
            Reminder Drafts & Log
          </button>
        </nav>

        <div className="msme-law-card">
          <div
            style={{
              fontWeight: 700,
              marginBottom: '0.25rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <ShieldAlert size={15} /> MSMED Act + Sec 43B(h)
          </div>
          <div>
            Statutory limit: <strong>45 days</strong> (written agreement) or <strong>15 days</strong>.
            Delayed interest: <strong>3× RBI Bank Rate (20.25% p.a.)</strong> compounded monthly.
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="main-area">
        <header className="topbar">
          <div>
            <h1 className="page-heading">
              {activeTab === 'dashboard' &&
                'Receivables Recovery, Action Queue & Cash-Flow Scenarios'}
              {activeTab === 'invoices' &&
                'Invoice Management, Priority Breakdown & Evidence Timeline'}
              {activeTab === 'customers' && 'MSME Buyer Directory & Observed Ledger History'}
              {activeTab === 'payments' && 'Recorded Collections & Duplicate-Protected UTR Ledger'}
              {activeTab === 'reminders' &&
                'Balance-Synchronized Reminder Generator & Immutable Snapshot Log'}
            </h1>
            <p className="page-subtitle">
              Turns receivables data into explainable collection actions and tracks what happens next
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
            <button
              className="btn btn-outline btn-sm"
              onClick={() => setShowWeightsModal(true)}
              title="Inspect & configure deterministic priority score weights"
            >
              <Sliders size={15} /> Priority Weights
            </button>
            <button
              className="btn btn-outline btn-sm"
              onClick={handleResetDemo}
              title="Reset synthetic demo data"
            >
              <RefreshCw size={15} /> Reset Demo
            </button>
            <button className="btn btn-outline btn-sm" onClick={() => setShowCustomerModal(true)}>
              <Plus size={15} /> Add Customer
            </button>
            <button className="btn btn-primary btn-sm" onClick={() => setShowInvoiceModal(true)}>
              <Plus size={15} /> New Invoice
            </button>
          </div>
        </header>

        {toast && (
          <div
            style={{
              background: '#0F766E',
              color: '#FFFFFF',
              padding: '0.75rem 2rem',
              fontSize: '0.9375rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.55rem',
            }}
          >
            <CheckCircle2 size={18} /> {toast}
          </div>
        )}

        <main className="content-container">
          {error ? (
            <div className="panel-card" style={{ borderColor: '#FECACA', background: '#FEF2F2' }}>
              <h3 className="card-heading" style={{ color: '#B91C1C', marginBottom: '0.5rem' }}>
                Backend Connection Needed
              </h3>
              <p style={{ fontSize: '0.95rem', marginBottom: '0.85rem', color: '#172B3A' }}>{error}</p>
              <button className="btn btn-primary btn-sm" onClick={loadAllData}>
                Retry Connection
              </button>
            </div>
          ) : loading && !dashboard ? (
            <div className="panel-card" style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>
              Loading PayTrack AI data...
            </div>
          ) : (
            <>
              {/* TAB 1: DASHBOARD */}
              {activeTab === 'dashboard' && dashboard && (
                <>
                  <div className="kpi-grid">
                    <div className="kpi-card">
                      <div className="kpi-label">
                        <span>Total Outstanding ({dashboard.kpis.open_invoices_count} Open)</span>
                        <IndianRupee size={18} color="#0F766E" />
                      </div>
                      <div className="kpi-value">{formatINR(dashboard.kpis.total_outstanding)}</div>
                      <div className="kpi-foot">
                        Overdue: <strong>{formatINR(dashboard.kpis.total_overdue)}</strong> (
                        {dashboard.kpis.overdue_invoices_count}) + Not Due:{' '}
                        <strong>{formatINR(dashboard.kpis.total_current_not_due)}</strong> (
                        {dashboard.kpis.current_not_due_count})
                      </div>
                    </div>

                    <div className="kpi-card kpi-danger">
                      <div className="kpi-label">
                        <span>Overdue Receivables</span>
                        <AlertTriangle size={18} color="#B91C1C" />
                      </div>
                      <div className="kpi-value" style={{ color: '#B91C1C' }}>
                        {formatINR(dashboard.kpis.total_overdue)}
                      </div>
                      <div className="kpi-foot">
                        Across <strong>{dashboard.kpis.overdue_invoices_count}</strong> invoices past
                        due date ({dashboard.kpis.collection_rate}% of{' '}
                        {formatINR(dashboard.kpis.total_invoiced)} collected)
                      </div>
                    </div>

                    <div className="kpi-card kpi-warning">
                      <div className="kpi-label">
                        <span>Est. MSMED Interest (20.25%)</span>
                        <Clock size={18} color="#B45309" />
                      </div>
                      <div className="kpi-value" style={{ color: '#B45309' }}>
                        {formatINR(dashboard.kpis.total_msmed_interest)}
                      </div>
                      <div className="kpi-foot">
                        Sec 16 monthly compound est. (3× {dashboard.kpis.rbi_bank_rate_percent}% RBI
                        rate assumption)
                      </div>
                    </div>

                    <div className="kpi-card kpi-teal">
                      <div className="kpi-label">
                        <span>Sec 43B(h) SLA Threshold</span>
                        <ShieldAlert size={18} color="#0F766E" />
                      </div>
                      <div className="kpi-value" style={{ color: '#115E59' }}>
                        {dashboard.kpis.section_43bh_count} Invoices
                      </div>
                      <div className="kpi-foot">
                        Overdue &gt;15d/45d since issue date • Est. Claim:{' '}
                        <strong>{formatINR(dashboard.kpis.total_claimable_with_interest)}</strong>
                      </div>
                    </div>
                  </div>

                  {dashboard.kpis.statutory_assumptions_note && (
                    <div className="statutory-banner">
                      <strong>Statutory Rules vs. Prototype Assumptions:</strong>{' '}
                      {dashboard.kpis.statutory_assumptions_note}
                    </div>
                  )}

                  {/* NEXT-BEST-ACTION QUEUE & EXPLAINABLE COLLECTION PRIORITY */}
                  <div className="panel-card">
                    <div className="panel-header">
                      <div>
                        <h2 className="panel-title">
                          <Sparkles size={20} color="#0F766E" /> Daily Next-Best-Action Queue
                          (Deterministic & Explainable Priority Scoring)
                        </h2>
                        <div className="panel-subtitle">
                          Rule-based score (0–100) = Overdue Severity (max{' '}
                          {dashboard.priority_weights.overdue_max_points} pts) + Balance Exposure (max{' '}
                          {dashboard.priority_weights.amount_max_points} pts) + Follow-Up/Partial
                          Status (max {dashboard.priority_weights.followup_max_points} pts)
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '0.55rem', flexWrap: 'wrap' }}>
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => setShowWeightsModal(true)}
                        >
                          <Sliders size={15} /> Configure Score Weights
                        </button>
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => setActiveTab('invoices')}
                        >
                          All Invoices <ArrowUpRight size={15} />
                        </button>
                      </div>
                    </div>

                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Priority & Score</th>
                            <th>Invoice & Buyer</th>
                            <th>Outstanding & Timing</th>
                            <th>Why It Appears in Queue (Deterministic Breakdown)</th>
                            <th>Recommended Next Action & Links</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dashboard.priority_queue.map((inv) => (
                            <tr key={inv.id}>
                              <td>
                                {renderPriorityBadge(inv.risk_level, inv.priority_score)}
                                <div
                                  className="num-tabular"
                                  style={{
                                    fontSize: '0.84rem',
                                    color: 'var(--text-muted)',
                                    marginTop: '0.35rem',
                                    fontWeight: 600,
                                  }}
                                >
                                  {inv.priority_breakdown.overdue_points}d +{' '}
                                  {inv.priority_breakdown.amount_points}₹ +{' '}
                                  {inv.priority_breakdown.followup_points}f pts
                                </div>
                              </td>
                              <td>
                                <div style={{ fontWeight: 700, fontSize: '0.96rem' }}>
                                  {inv.invoice_number}
                                </div>
                                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                                  {inv.company_name}
                                </div>
                              </td>
                              <td>
                                <div
                                  className="num-tabular"
                                  style={{ fontWeight: 800, fontSize: '1rem' }}
                                >
                                  {formatINR(inv.balance_due)}
                                </div>
                                {inv.msmed_interest > 0 && (
                                  <div
                                    className="num-tabular"
                                    style={{
                                      fontSize: '0.84rem',
                                      color: 'var(--amber)',
                                      fontWeight: 600,
                                      marginTop: '0.15rem',
                                    }}
                                  >
                                    + {formatINR(inv.msmed_interest)} Sec 16 int.
                                  </div>
                                )}
                                <div style={{ marginTop: '0.3rem' }}>
                                  {inv.days_overdue > 0 ? (
                                    <span className="badge badge-overdue">
                                      {inv.days_overdue}d Overdue
                                    </span>
                                  ) : (
                                    <span className="badge badge-pending">
                                      Due in {inv.days_until_due}d
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td style={{ maxWidth: '390px' }}>
                                {(() => {
                                  const followupMax = dashboard.priority_weights?.followup_max_points ?? 20;
                                  const { factors: recFactors, points: recPts } = getReconciledFactors(inv, followupMax);
                                  const followupSubPts = recPts.slice(2);
                                  return (
                                    <>
                                      <div
                                        style={{
                                          fontSize: '0.875rem',
                                          fontWeight: 600,
                                          color: 'var(--text-main)',
                                          marginBottom: '0.3rem',
                                        }}
                                      >
                                        {inv.priority_explanation}
                                      </div>
                                      <ul
                                        style={{
                                          fontSize: '0.84rem',
                                          color: 'var(--text-muted)',
                                          paddingLeft: '1.1rem',
                                          margin: 0,
                                          lineHeight: 1.45,
                                        }}
                                      >
                                        {recFactors.map((f, idx) => (
                                          <li key={idx}>{f}</li>
                                        ))}
                                      </ul>
                                      {recPts.length > 0 && (
                                        <div
                                          className="num-tabular"
                                          style={{
                                            fontSize: '0.82rem',
                                            color: 'var(--primary-hover)',
                                            marginTop: '0.35rem',
                                            fontWeight: 700,
                                          }}
                                        >
                                          Reconciled sum: {recPts.join(' + ')} = {inv.priority_score}/100 pts
                                          {followupSubPts.length > 1
                                            ? ` (Follow-up sub-factors: ${followupSubPts.join(' + ')} = ${inv.priority_breakdown.followup_points}/${followupMax} pts)`
                                            : ''}
                                        </div>
                                      )}
                                    </>
                                  );
                                })()}
                              </td>
                              <td>
                                <div
                                  style={{
                                    fontSize: '0.88rem',
                                    fontWeight: 700,
                                    color: 'var(--primary-hover)',
                                    marginBottom: '0.55rem',
                                  }}
                                >
                                  {inv.ai_recommended_action}
                                </div>
                                <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                                  <button
                                    className="btn btn-primary btn-sm"
                                    onClick={() => openReminderForInvoice(inv)}
                                  >
                                    Draft Reminder
                                  </button>
                                  <button
                                    className="btn btn-emerald btn-sm"
                                    onClick={() => openPaymentModal(inv)}
                                  >
                                    Record Payment
                                  </button>
                                  <button
                                    className="btn btn-outline btn-sm"
                                    onClick={() => openWorkspaceModal(inv.id)}
                                  >
                                    <History size={14} /> Timeline & Evidence
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* TWO-COL: TRANSPARENT 30-DAY CASH-FLOW SCENARIOS + AGING BREAKDOWN */}
                  <div className="two-col-grid">
                    <div className="panel-card">
                      <div className="panel-header">
                        <h2 className="panel-title">
                          <TrendingUp size={20} color="#0F766E" /> Transparent 30-Day Cash-Inflow
                          Scenarios (Estimates)
                        </h2>
                        <span className="badge badge-pending">Rule-Based Estimates</span>
                      </div>

                      {dashboard.cashflow_scenarios.insufficient_historical_data && (
                        <div
                          style={{
                            background: 'var(--amber-soft)',
                            border: '1px solid var(--amber-border)',
                            borderRadius: '8px',
                            padding: '0.75rem 0.95rem',
                            fontSize: '0.86rem',
                            color: 'var(--amber)',
                            marginBottom: '1.1rem',
                            display: 'flex',
                            gap: '0.55rem',
                            alignItems: 'flex-start',
                          }}
                        >
                          <Info size={17} style={{ flexShrink: 0, marginTop: '2px' }} />
                          <div>
                            <strong>Data Limitation Notice:</strong>{' '}
                            {dashboard.cashflow_scenarios.methodology_disclaimer}
                          </div>
                        </div>
                      )}

                      <div className="scenario-grid">
                        {[
                          {
                            band: dashboard.cashflow_scenarios.conservative,
                            cls: 'scenario-conservative',
                            accent: '#526575',
                          },
                          {
                            band: dashboard.cashflow_scenarios.baseline,
                            cls: 'scenario-baseline',
                            accent: '#0F766E',
                          },
                          {
                            band: dashboard.cashflow_scenarios.optimistic,
                            cls: 'scenario-optimistic',
                            accent: '#047857',
                          },
                        ].map(({ band, cls, accent }) => (
                          <div key={band.name} className={`scenario-card ${cls}`}>
                            <div>
                              <h3 className="scenario-title" style={{ color: accent }}>
                                {band.name}
                              </h3>
                              <div className="scenario-value">
                                {formatINR(band.expected_inflow_30d)}
                              </div>
                              <div
                                className="num-tabular"
                                style={{
                                  fontSize: '0.85rem',
                                  color: 'var(--text-main)',
                                  fontWeight: 600,
                                }}
                              >
                                {band.collection_share_of_outstanding_pct}% of current principal (
                                {formatINR(band.expected_principal_inflow_30d)}
                                {band.expected_interest_inflow_30d > 0
                                  ? ` + ${formatINR(band.expected_interest_inflow_30d)} est. int.`
                                  : ''}
                                )
                              </div>
                            </div>
                            <div
                              style={{
                                fontSize: '0.82rem',
                                color: 'var(--text-muted)',
                                marginTop: '0.6rem',
                                lineHeight: 1.45,
                              }}
                            >
                              {band.assumptions_summary}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Aging Buckets */}
                    <div className="panel-card">
                      <div className="panel-header">
                        <h2 className="panel-title">Receivables Aging & 45-Day MSME SLA</h2>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
                        {dashboard.aging_breakdown.map((b) => {
                          const maxVal = Math.max(1, dashboard.kpis.total_outstanding);
                          const pct = Math.min(100, Math.round((b.amount / maxVal) * 100));
                          const isCritical = b.bucket.includes('45+');
                          return (
                            <div key={b.bucket}>
                              <div
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  fontSize: '0.92rem',
                                  marginBottom: '0.35rem',
                                }}
                              >
                                <span style={{ fontWeight: 600 }}>
                                  {b.bucket}{' '}
                                  <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
                                    ({b.count} inv)
                                  </span>
                                </span>
                                <span
                                  className="num-tabular"
                                  style={{
                                    fontWeight: 700,
                                    color: isCritical ? 'var(--crimson)' : 'var(--text-main)',
                                  }}
                                >
                                  {formatINR(b.amount)}
                                </span>
                              </div>
                              <div
                                style={{
                                  height: '11px',
                                  background: 'var(--bg-subtle)',
                                  borderRadius: '999px',
                                  overflow: 'hidden',
                                }}
                              >
                                <div
                                  style={{
                                    width: `${pct}%`,
                                    height: '100%',
                                    background: isCritical
                                      ? 'var(--crimson)'
                                      : b.bucket.includes('Current')
                                      ? 'var(--primary)'
                                      : 'var(--amber)',
                                    borderRadius: '999px',
                                  }}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* TAB 2: INVOICES & OVERDUE TRACKING */}
              {activeTab === 'invoices' && (
                <div className="panel-card">
                  <div className="panel-header">
                    <h2 className="panel-title">
                      <FileText size={20} color="#0F766E" /> All MSME Invoices, Explainable Priority &
                      Follow-Up Workspace
                    </h2>
                    <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
                      {['ALL', 'OVERDUE', 'PARTIALLY PAID', 'PENDING', 'PAID', '43BH'].map((st) => (
                        <button
                          key={st}
                          className={`btn btn-sm ${
                            statusFilter === st ? 'btn-primary' : 'btn-outline'
                          }`}
                          onClick={() => setStatusFilter(st)}
                        >
                          {st === '43BH' ? 'Sec 43B(h) Risk' : st}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Invoice #</th>
                          <th>Buyer Company</th>
                          <th>Issue / Due Date</th>
                          <th>Billed / Paid</th>
                          <th>Balance Due</th>
                          <th>MSMED Interest (20.25%)</th>
                          <th>Status & Priority Score</th>
                          <th>Next Action & Evidence Workspace</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredInvoices.map((inv) => (
                          <tr key={inv.id}>
                            <td>
                              <div style={{ fontWeight: 700, fontSize: '0.96rem' }}>
                                {inv.invoice_number}
                              </div>
                              <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>
                                {inv.msme_agreement ? '45d MSME SLA' : '15d No-Agreement SLA'}
                              </div>
                            </td>
                            <td>
                              <div style={{ fontWeight: 600 }}>{inv.company_name}</div>
                              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                {inv.description}
                              </div>
                            </td>
                            <td className="num-tabular">
                              <div>
                                Due: <strong>{inv.due_date}</strong>
                              </div>
                              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                Issued: {inv.issue_date}
                              </div>
                            </td>
                            <td className="num-tabular">
                              <div style={{ fontWeight: 600 }}>{formatINR(inv.total_amount)}</div>
                              {inv.amount_paid > 0 && (
                                <div
                                  style={{
                                    fontSize: '0.84rem',
                                    color: 'var(--emerald)',
                                    fontWeight: 600,
                                  }}
                                >
                                  Paid: {formatINR(inv.amount_paid)} ({inv.payments_recorded_count})
                                </div>
                              )}
                            </td>
                            <td className="num-tabular" style={{ fontWeight: 800, fontSize: '1rem' }}>
                              {formatINR(inv.balance_due)}
                            </td>
                            <td className="num-tabular">
                              {inv.msmed_interest > 0 ? (
                                <div>
                                  <div style={{ color: 'var(--crimson)', fontWeight: 700 }}>
                                    +{formatINR(inv.msmed_interest)}
                                  </div>
                                  <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>
                                    Total: {formatINR(inv.total_claimable)}
                                  </div>
                                </div>
                              ) : (
                                <span style={{ color: 'var(--text-muted)' }}>₹0</span>
                              )}
                            </td>
                            <td>
                              <div
                                style={{
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: '0.3rem',
                                  alignItems: 'flex-start',
                                }}
                              >
                                {renderStatusBadge(inv.status)}
                                {inv.balance_due > 0 &&
                                  renderPriorityBadge(inv.risk_level, inv.priority_score)}
                                {inv.days_overdue > 0 ? (
                                  <span
                                    style={{
                                      fontSize: '0.84rem',
                                      fontWeight: 600,
                                      color: 'var(--crimson)',
                                    }}
                                  >
                                    {inv.days_overdue} days overdue
                                  </span>
                                ) : inv.balance_due > 0 ? (
                                  <span style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>
                                    Due in {inv.days_until_due} days
                                  </span>
                                ) : null}
                                {inv.section_43bh_at_risk && (
                                  <span className="badge badge-43bh">43B(h) Threshold</span>
                                )}
                              </div>
                            </td>
                            <td>
                              <div
                                style={{
                                  fontSize: '0.88rem',
                                  color: 'var(--primary-hover)',
                                  fontWeight: 700,
                                  marginBottom: '0.25rem',
                                }}
                              >
                                {inv.ai_recommended_action}
                              </div>
                              <div
                                style={{
                                  fontSize: '0.84rem',
                                  color: 'var(--text-muted)',
                                  marginBottom: '0.5rem',
                                }}
                              >
                                {inv.priority_explanation}
                              </div>
                              <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                                <button
                                  className="btn btn-outline btn-sm"
                                  onClick={() => openWorkspaceModal(inv.id)}
                                >
                                  <FolderCheck size={14} /> Timeline & Evidence
                                </button>
                                {inv.balance_due > 0 && (
                                  <>
                                    <button
                                      className="btn btn-emerald btn-sm"
                                      onClick={() => openPaymentModal(inv)}
                                    >
                                      Record Payment
                                    </button>
                                    <button
                                      className="btn btn-primary btn-sm"
                                      onClick={() => openReminderForInvoice(inv)}
                                    >
                                      Draft Reminder
                                    </button>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 3: CUSTOMERS */}
              {activeTab === 'customers' && (
                <div className="panel-card">
                  <div className="panel-header">
                    <div>
                      <h2 className="panel-title">
                        <Building2 size={20} color="#0F766E" /> Registered Buyer Accounts & Observed
                        Ledger Status
                      </h2>
                      <div className="panel-subtitle">
                        Shows verified invoice & payment counts rather than unvalidated predictive
                        reliability scores on small sample sizes.
                      </div>
                    </div>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => setShowCustomerModal(true)}
                    >
                      <Plus size={15} /> Add New Customer
                    </button>
                  </div>

                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Company & Contact</th>
                          <th>GSTIN & Udyam ID</th>
                          <th>City & Credit SLA</th>
                          <th>Total Billed / Paid</th>
                          <th>Outstanding / Overdue</th>
                          <th>Observed Ledger Status & Data Note</th>
                        </tr>
                      </thead>
                      <tbody>
                        {customers.map((c) => (
                          <tr key={c.id}>
                            <td>
                              <div style={{ fontWeight: 700, fontSize: '0.96rem' }}>
                                {c.company_name}
                              </div>
                              <div style={{ fontSize: '0.86rem', color: 'var(--text-muted)' }}>
                                {c.name} • {c.phone}
                              </div>
                            </td>
                            <td>
                              <div
                                style={{
                                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                                  fontWeight: 600,
                                  fontSize: '0.9rem',
                                }}
                              >
                                {c.gstin}
                              </div>
                              <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>
                                {c.udyam_number || 'Corporate Buyer'}
                              </div>
                            </td>
                            <td>
                              <div style={{ fontWeight: 600 }}>{c.city}</div>
                              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                {c.credit_period_days} Days Credit Term
                              </div>
                            </td>
                            <td className="num-tabular">
                              <div>Billed: {formatINR(c.total_invoiced)}</div>
                              <div
                                style={{
                                  fontSize: '0.86rem',
                                  color: 'var(--emerald)',
                                  fontWeight: 600,
                                }}
                              >
                                Paid: {formatINR(c.total_paid)}
                              </div>
                            </td>
                            <td className="num-tabular">
                              <div style={{ fontWeight: 800, fontSize: '1rem' }}>
                                {formatINR(c.total_outstanding)}
                              </div>
                              {c.overdue_amount > 0 && (
                                <div
                                  style={{
                                    fontSize: '0.85rem',
                                    color: 'var(--crimson)',
                                    fontWeight: 600,
                                  }}
                                >
                                  Overdue: {formatINR(c.overdue_amount)} ({c.overdue_invoices_count})
                                </div>
                              )}
                            </td>
                            <td style={{ maxWidth: '320px' }}>
                              <span
                                className={`badge ${
                                  c.overdue_invoices_count === 0
                                    ? 'badge-paid'
                                    : c.risk_badge.includes('>45d')
                                    ? 'badge-overdue'
                                    : 'badge-partial'
                                }`}
                              >
                                {c.risk_badge}
                              </span>
                              <div
                                style={{
                                  fontSize: '0.84rem',
                                  color: 'var(--text-muted)',
                                  marginTop: '0.35rem',
                                  lineHeight: 1.45,
                                }}
                              >
                                {c.historical_data_note}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 4: PAYMENTS LEDGER */}
              {activeTab === 'payments' && (
                <div className="panel-card">
                  <div className="panel-header">
                    <h2 className="panel-title">
                      <IndianRupee size={20} color="#0F766E" /> Recorded Payment Receipts &
                      Duplicate-Protected UTR History
                    </h2>
                  </div>

                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Payment Date</th>
                          <th>Invoice Number</th>
                          <th>Buyer Company</th>
                          <th>Amount Received</th>
                          <th>Mode</th>
                          <th>UTR / Reference No.</th>
                          <th>Remarks</th>
                        </tr>
                      </thead>
                      <tbody>
                        {payments.map((p) => (
                          <tr key={p.id}>
                            <td className="num-tabular" style={{ fontWeight: 600 }}>
                              {p.payment_date}
                            </td>
                            <td style={{ fontWeight: 700 }}>{p.invoice_number}</td>
                            <td>{p.company_name}</td>
                            <td
                              className="num-tabular"
                              style={{ fontWeight: 800, color: 'var(--emerald)', fontSize: '1rem' }}
                            >
                              +{formatINR(p.amount)}
                            </td>
                            <td>
                              <span className="badge badge-pending">{p.payment_mode}</span>
                            </td>
                            <td
                              style={{
                                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                                fontSize: '0.9rem',
                              }}
                            >
                              {p.reference_number || '—'}
                            </td>
                            <td style={{ color: 'var(--text-muted)' }}>{p.notes || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 5: AI REMINDER DRAFTS & IMMUTABLE SNAPSHOT LOG */}
              {activeTab === 'reminders' && (
                <div className="two-col-grid">
                  <div className="panel-card">
                    <div className="panel-header">
                      <h2 className="panel-title">
                        <Sparkles size={20} color="#0F766E" /> Balance-Synchronized Reminder
                        Generator
                      </h2>
                      {selectedReminderInvoice && (
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => openWorkspaceModal(selectedReminderInvoice.id)}
                        >
                          <History size={15} /> Open Invoice Timeline
                        </button>
                      )}
                    </div>

                    <div className="form-group">
                      <label>1. Select Unpaid / Overdue Invoice</label>
                      <select
                        className="form-select"
                        value={selectedReminderInvoiceId}
                        onChange={(e) => setSelectedReminderInvoiceId(Number(e.target.value))}
                      >
                        {invoices
                          .filter((i) => i.balance_due > 0)
                          .map((inv) => (
                            <option key={inv.id} value={inv.id}>
                              {inv.invoice_number} — {inv.company_name} (Live Balance:{' '}
                              {formatINR(inv.balance_due)} |{' '}
                              {inv.days_overdue > 0
                                ? `${inv.days_overdue}d overdue`
                                : `Due in ${inv.days_until_due}d`}
                              )
                            </option>
                          ))}
                      </select>
                    </div>

                    <div className="form-grid">
                      <div className="form-group">
                        <label>2. Escalation Tone</label>
                        <select
                          className="form-select"
                          value={reminderTone}
                          onChange={(e) => setReminderTone(e.target.value)}
                        >
                          <option value="Polite">Polite (Relationship-First)</option>
                          <option value="Firm">Firm (Overdue + Interest Statement)</option>
                          <option value="Statutory MSME">
                            Statutory MSME (Sec 16 + Sec 43B(h) Intimation)
                          </option>
                        </select>
                      </div>

                      <div className="form-group">
                        <label>3. Delivery Channel</label>
                        <select
                          className="form-select"
                          value={reminderChannel}
                          onChange={(e) => setReminderChannel(e.target.value)}
                        >
                          <option value="WhatsApp">WhatsApp Business Message</option>
                          <option value="Email">Formal Accounts Email / Intimation</option>
                        </select>
                      </div>
                    </div>

                    {currentDraft && (
                      <>
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(3, 1fr)',
                            gap: '0.8rem',
                            background: 'var(--bg-subtle)',
                            border: '1px solid var(--border-color)',
                            borderRadius: '10px',
                            padding: '0.9rem 1rem',
                            marginBottom: '0.9rem',
                          }}
                        >
                          <div>
                            <div
                              style={{
                                color: 'var(--text-muted)',
                                fontWeight: 600,
                                fontSize: '0.84rem',
                              }}
                            >
                              Live Principal Balance
                            </div>
                            <div
                              className="num-tabular"
                              style={{
                                fontWeight: 800,
                                fontSize: '1.15rem',
                                color: 'var(--text-main)',
                                marginTop: '0.15rem',
                              }}
                            >
                              {formatINR(currentDraft.balance_due)}
                            </div>
                          </div>
                          <div>
                            <div
                              style={{
                                color: 'var(--text-muted)',
                                fontWeight: 600,
                                fontSize: '0.84rem',
                              }}
                            >
                              MSMED Interest (20.25%)
                            </div>
                            <div
                              className="num-tabular"
                              style={{
                                fontWeight: 800,
                                fontSize: '1.15rem',
                                color: 'var(--amber)',
                                marginTop: '0.15rem',
                              }}
                            >
                              +{formatINR(currentDraft.msmed_interest)}
                            </div>
                          </div>
                          <div>
                            <div
                              style={{
                                color: 'var(--text-muted)',
                                fontWeight: 600,
                                fontSize: '0.84rem',
                              }}
                            >
                              Total Payable
                            </div>
                            <div
                              className="num-tabular"
                              style={{
                                fontWeight: 800,
                                fontSize: '1.15rem',
                                color: 'var(--crimson)',
                                marginTop: '0.15rem',
                              }}
                            >
                              {formatINR(currentDraft.total_claimable)}
                            </div>
                          </div>
                        </div>

                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            background: 'var(--primary-tint)',
                            border: '1px solid var(--primary-border)',
                            borderRadius: '8px',
                            padding: '0.75rem 0.95rem',
                            fontSize: '0.875rem',
                            color: 'var(--primary-hover)',
                            marginBottom: '1rem',
                            gap: '0.6rem',
                            flexWrap: 'wrap',
                          }}
                        >
                          <div>
                            <strong>Rationale:</strong> {currentDraft.ai_rationale}
                          </div>
                          <span className="badge badge-pending">
                            {draftWasEdited
                              ? 'Status: Draft Edited (Not Sent)'
                              : currentDraft.delivery_status}
                          </span>
                        </div>

                        <div className="form-group">
                          <label>Subject Line</label>
                          <input
                            className="form-input"
                            value={currentDraft.subject}
                            onChange={(e) => {
                              setDraftWasEdited(true);
                              setCurrentDraft({ ...currentDraft, subject: e.target.value });
                            }}
                          />
                        </div>

                        <div className="form-group">
                          <label>Drafted Message Body (Editable)</label>
                          <textarea
                            className="form-textarea"
                            rows={11}
                            value={currentDraft.message_body}
                            onChange={(e) => {
                              setDraftWasEdited(true);
                              setCurrentDraft({ ...currentDraft, message_body: e.target.value });
                            }}
                          />
                        </div>

                        <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
                          <button
                            className="btn btn-primary"
                            onClick={() => {
                              navigator.clipboard.writeText(
                                `${currentDraft.subject}\n\n${currentDraft.message_body}`
                              );
                              showToastMsg('Reminder copied to clipboard for manual sending!');
                            }}
                          >
                            <Copy size={16} /> Copy Draft Text
                          </button>
                          <button className="btn btn-emerald" onClick={handleLogReminder}>
                            <Send size={16} /> Log Follow-Up Snapshot (Simulated Send)
                          </button>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Reminder History with Immutable Snapshots */}
                  <div className="panel-card">
                    <div className="panel-header">
                      <div>
                        <h2 className="panel-title">
                          Immutable Follow-Up & Reminder Snapshot Log
                        </h2>
                        <div className="panel-subtitle">
                          Historical snapshots preserve the exact invoice balance at the moment a
                          reminder was logged, even after subsequent payments.
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.95rem' }}>
                      {reminders.map((r) => (
                        <div
                          key={r.id}
                          style={{
                            border: '1px solid var(--border-color)',
                            borderRadius: '10px',
                            padding: '1.05rem',
                            background: 'var(--bg-subtle)',
                          }}
                        >
                          <div
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              marginBottom: '0.45rem',
                              flexWrap: 'wrap',
                              gap: '0.4rem',
                            }}
                          >
                            <span style={{ fontWeight: 700, fontSize: '0.96rem' }}>
                              {r.invoice_number} • {r.company_name}
                            </span>
                            <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                              <span className="badge badge-pending">
                                {r.channel} ({r.tone})
                              </span>
                              <span className="badge badge-partial">{r.delivery_status}</span>
                            </div>
                          </div>

                          {r.snapshot_balance_due !== undefined && r.snapshot_balance_due !== null && (
                            <div
                              className="num-tabular"
                              style={{
                                fontSize: '0.85rem',
                                color: 'var(--primary-hover)',
                                background: 'var(--primary-tint)',
                                border: '1px solid var(--primary-border)',
                                padding: '0.4rem 0.65rem',
                                borderRadius: '6px',
                                marginBottom: '0.5rem',
                                fontWeight: 600,
                              }}
                            >
                              Immutable Snapshot at Log Time: Principal{' '}
                              {formatINR(r.snapshot_balance_due)} | Interest{' '}
                              {formatINR(r.snapshot_interest || 0)} | Total{' '}
                              {formatINR(r.snapshot_total_claimable || r.snapshot_balance_due)}
                            </div>
                          )}

                          <div
                            style={{
                              fontSize: '0.92rem',
                              fontWeight: 700,
                              marginBottom: '0.3rem',
                              color: 'var(--text-main)',
                            }}
                          >
                            {r.subject}
                          </div>
                          <div
                            style={{
                              fontSize: '0.86rem',
                              color: 'var(--text-muted)',
                              whiteSpace: 'pre-line',
                              lineHeight: 1.5,
                            }}
                          >
                            {r.message_body.slice(0, 240)}
                            {r.message_body.length > 240 ? '...' : ''}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </main>
      </div>

      {/* MODAL: INVOICE DETAIL, TIMELINE & EVIDENCE WORKSPACE */}
      {(workspaceData || workspaceLoading) && (
        <div className="modal-backdrop" onClick={() => setWorkspaceData(null)}>
          <div
            className="modal-card"
            style={{ maxWidth: '900px' }}
            onClick={(e) => e.stopPropagation()}
          >
            {workspaceLoading || !workspaceData ? (
              <div style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>
                Loading Invoice Timeline & Evidence Workspace...
              </div>
            ) : (
              <>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: '1.15rem',
                    borderBottom: '1px solid var(--border-color)',
                    paddingBottom: '0.9rem',
                  }}
                >
                  <div>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.55rem',
                        flexWrap: 'wrap',
                      }}
                    >
                      <h3 className="modal-title">
                        {workspaceData.invoice.invoice_number} — Evidence & Follow-Up Workspace
                      </h3>
                      {renderStatusBadge(workspaceData.invoice.status)}
                      {workspaceData.invoice.balance_due > 0 &&
                        renderPriorityBadge(
                          workspaceData.invoice.risk_level,
                          workspaceData.invoice.priority_score
                        )}
                    </div>
                    <p
                      style={{
                        fontSize: '0.9rem',
                        color: 'var(--text-muted)',
                        marginTop: '0.25rem',
                      }}
                    >
                      {workspaceData.invoice.company_name} (GSTIN:{' '}
                      {workspaceData.invoice.customer_gstin} • Udyam:{' '}
                      {workspaceData.invoice.customer_udyam || 'N/A'})
                    </p>
                  </div>
                  <button className="btn btn-outline btn-sm" onClick={() => setWorkspaceData(null)}>
                    Close
                  </button>
                </div>

                {/* Summary Bar */}
                <div className="workspace-summary-grid">
                  <div className="workspace-stat-card">
                    <div className="workspace-stat-label">Original Invoice Total</div>
                    <div className="workspace-stat-value">
                      {formatINR(workspaceData.invoice.total_amount)}
                    </div>
                  </div>
                  <div
                    className="workspace-stat-card"
                    style={{
                      background: 'var(--emerald-soft)',
                      borderColor: 'var(--emerald-border)',
                    }}
                  >
                    <div className="workspace-stat-label" style={{ color: 'var(--emerald)' }}>
                      Reconciled Payments ({workspaceData.payments.length})
                    </div>
                    <div className="workspace-stat-value" style={{ color: 'var(--emerald)' }}>
                      {formatINR(workspaceData.invoice.amount_paid)}
                    </div>
                  </div>
                  <div
                    className="workspace-stat-card"
                    style={{
                      background: 'var(--crimson-soft)',
                      borderColor: 'var(--crimson-border)',
                    }}
                  >
                    <div className="workspace-stat-label" style={{ color: 'var(--crimson)' }}>
                      Current Principal Balance
                    </div>
                    <div className="workspace-stat-value" style={{ color: 'var(--crimson)' }}>
                      {formatINR(workspaceData.invoice.balance_due)}
                    </div>
                  </div>
                  <div
                    className="workspace-stat-card"
                    style={{
                      background: 'var(--amber-soft)',
                      borderColor: 'var(--amber-border)',
                    }}
                  >
                    <div className="workspace-stat-label" style={{ color: 'var(--amber)' }}>
                      Total + Sec 16 Interest
                    </div>
                    <div className="workspace-stat-value" style={{ color: 'var(--amber)' }}>
                      {formatINR(workspaceData.invoice.total_claimable)}
                    </div>
                  </div>
                </div>

                {/* Section 1: Chronological Payment-Aware Follow-Up Timeline */}
                <div style={{ marginBottom: '1.35rem' }}>
                  <h4 className="card-heading" style={{ marginBottom: '0.65rem' }}>
                    1. Chronological Payment-Aware Follow-Up Timeline ({workspaceData.timeline.length}{' '}
                    Events)
                  </h4>
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.6rem',
                      maxHeight: '260px',
                      overflowY: 'auto',
                      paddingRight: '0.25rem',
                    }}
                  >
                    {workspaceData.timeline.map((ev) => (
                      <div
                        key={ev.id}
                        style={{
                          borderLeft:
                            ev.event_type === 'PAYMENT_RECEIVED' ||
                            ev.event_type === 'BALANCE_UPDATED'
                              ? '3px solid var(--emerald)'
                              : ev.event_type.startsWith('REMINDER')
                              ? '3px solid var(--amber)'
                              : '3px solid var(--primary)',
                          background: 'var(--bg-subtle)',
                          padding: '0.65rem 0.9rem',
                          borderRadius: '0 8px 8px 0',
                          fontSize: '0.875rem',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            fontWeight: 700,
                            marginBottom: '0.2rem',
                            gap: '0.5rem',
                            flexWrap: 'wrap',
                          }}
                        >
                          <span>
                            [{ev.event_type}] {ev.title}
                          </span>
                          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                            {new Date(ev.created_at).toLocaleString('en-IN')} • {ev.delivery_status}
                          </span>
                        </div>
                        <div style={{ color: 'var(--text-muted)', lineHeight: 1.45 }}>
                          {ev.details}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Section 2: Administrative Evidence & Follow-Up Readiness Checklist */}
                <div style={{ marginBottom: '1.15rem' }}>
                  <h4 className="card-heading" style={{ marginBottom: '0.65rem' }}>
                    2. Supporting Evidence & Administrative Readiness Checklist
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
                    {workspaceData.evidence_checklist.map((item) => (
                      <div
                        key={item.item_key}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '0.65rem 0.9rem',
                          border: '1px solid var(--border-color)',
                          borderRadius: '8px',
                          fontSize: '0.88rem',
                          gap: '0.75rem',
                        }}
                      >
                        <div>
                          <div style={{ fontWeight: 700 }}>{item.label}</div>
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
                            {item.details}
                          </div>
                        </div>
                        <span
                          className={`badge ${
                            item.status === 'Available in System' ? 'badge-paid' : 'badge-partial'
                          }`}
                        >
                          {item.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Legal / Scope Disclaimer */}
                <div
                  style={{
                    background: 'var(--bg-subtle)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    padding: '0.75rem 0.95rem',
                    fontSize: '0.84rem',
                    color: 'var(--text-muted)',
                    marginBottom: '1.1rem',
                    lineHeight: 1.45,
                  }}
                >
                  {workspaceData.legal_disclaimer}
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.55rem' }}>
                  {workspaceData.invoice.balance_due > 0 && (
                    <>
                      <button
                        className="btn btn-emerald btn-sm"
                        onClick={() => {
                          const inv = workspaceData.invoice;
                          setWorkspaceData(null);
                          openPaymentModal(inv);
                        }}
                      >
                        Record Payment
                      </button>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => {
                          const inv = workspaceData.invoice;
                          setWorkspaceData(null);
                          openReminderForInvoice(inv);
                        }}
                      >
                        Draft Updated Reminder
                      </button>
                    </>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* MODAL: CONFIGURE DETERMINISTIC PRIORITY SCORE WEIGHTS */}
      {showWeightsModal && (
        <div className="modal-backdrop" onClick={() => setShowWeightsModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title" style={{ marginBottom: '0.35rem' }}>
              Configure Deterministic Priority Score Weights
            </h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginBottom: '1.15rem' }}>
              PayTrack AI uses a transparent rule-based formula rather than an opaque black-box score.
              Adjust the weights below to customize how overdue invoices are ranked.
            </p>
            <form onSubmit={handleSavePriorityWeights}>
              <div className="form-grid">
                <div className="form-group">
                  <label>Max Overdue Severity Points</label>
                  <input
                    type="number"
                    min={10}
                    max={80}
                    className="form-input"
                    value={weightsForm.overdue_max_points}
                    onChange={(e) =>
                      setWeightsForm({
                        ...weightsForm,
                        overdue_max_points: Number(e.target.value),
                      })
                    }
                  />
                </div>
                <div className="form-group">
                  <label>Points per Overdue Day</label>
                  <input
                    type="number"
                    step="0.1"
                    min={0.1}
                    max={5}
                    className="form-input"
                    value={weightsForm.overdue_points_per_day}
                    onChange={(e) =>
                      setWeightsForm({
                        ...weightsForm,
                        overdue_points_per_day: Number(e.target.value),
                      })
                    }
                  />
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group">
                  <label>Max Amount Exposure Points</label>
                  <input
                    type="number"
                    min={10}
                    max={60}
                    className="form-input"
                    value={weightsForm.amount_max_points}
                    onChange={(e) =>
                      setWeightsForm({
                        ...weightsForm,
                        amount_max_points: Number(e.target.value),
                      })
                    }
                  />
                </div>
                <div className="form-group">
                  <label>Reference Cap Amount (₹)</label>
                  <input
                    type="number"
                    step="10000"
                    min={10000}
                    className="form-input"
                    value={weightsForm.amount_reference_cap_inr}
                    onChange={(e) =>
                      setWeightsForm({
                        ...weightsForm,
                        amount_reference_cap_inr: Number(e.target.value),
                      })
                    }
                  />
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group">
                  <label>Max Follow-Up Status Points</label>
                  <input
                    type="number"
                    min={5}
                    max={40}
                    className="form-input"
                    value={weightsForm.followup_max_points}
                    onChange={(e) =>
                      setWeightsForm({
                        ...weightsForm,
                        followup_max_points: Number(e.target.value),
                      })
                    }
                  />
                </div>
                <div className="form-group">
                  <label>Pre-Due Reminder Window (Days)</label>
                  <input
                    type="number"
                    min={1}
                    max={15}
                    className="form-input"
                    value={weightsForm.pre_due_window_days}
                    onChange={(e) =>
                      setWeightsForm({
                        ...weightsForm,
                        pre_due_window_days: Number(e.target.value),
                      })
                    }
                  />
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginTop: '1.15rem',
                }}
              >
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={handleResetPriorityWeights}
                >
                  Restore Defaults
                </button>
                <div style={{ display: 'flex', gap: '0.55rem' }}>
                  <button
                    type="button"
                    className="btn btn-outline"
                    onClick={() => setShowWeightsModal(false)}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary">
                    Save & Recalculate Queue
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 1: RECORD PAYMENT */}
      {paymentModalInvoice && (
        <div className="modal-backdrop" onClick={() => setPaymentModalInvoice(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title" style={{ marginBottom: '0.35rem' }}>
              Record Payment — {paymentModalInvoice.invoice_number}
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '1.15rem' }}>
              {paymentModalInvoice.company_name} • Balance Due:{' '}
              <strong className="num-tabular">{formatINR(paymentModalInvoice.balance_due)}</strong>
            </p>

            <form onSubmit={handleRecordPayment}>
              <div className="form-grid">
                <div className="form-group">
                  <label>Amount Received (₹)</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    max={paymentModalInvoice.balance_due}
                    className="form-input"
                    value={payForm.amount}
                    onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Payment Date</label>
                  <input
                    type="date"
                    required
                    className="form-input"
                    value={payForm.payment_date}
                    onChange={(e) => setPayForm({ ...payForm, payment_date: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group">
                  <label>Payment Mode</label>
                  <select
                    className="form-select"
                    value={payForm.payment_mode}
                    onChange={(e) => setPayForm({ ...payForm, payment_mode: e.target.value })}
                  >
                    <option value="NEFT">NEFT</option>
                    <option value="RTGS">RTGS</option>
                    <option value="UPI">Corporate UPI</option>
                    <option value="Cheque">Cheque / DD</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>UTR / Reference Number (Duplicate-Checked)</label>
                  <input
                    type="text"
                    className="form-input"
                    value={payForm.reference_number}
                    onChange={(e) => setPayForm({ ...payForm, reference_number: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <input
                  type="text"
                  className="form-input"
                  value={payForm.notes}
                  onChange={(e) => setPayForm({ ...payForm, notes: e.target.value })}
                />
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '0.6rem',
                  marginTop: '1.15rem',
                }}
              >
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => setPaymentModalInvoice(null)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-emerald">
                  Save Payment Receipt
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: CREATE INVOICE */}
      {showInvoiceModal && (
        <div className="modal-backdrop" onClick={() => setShowInvoiceModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title" style={{ marginBottom: '1.15rem' }}>
              Create New GST Tax Invoice
            </h3>
            <form onSubmit={handleCreateInvoice}>
              <div className="form-grid">
                <div className="form-group">
                  <label>Invoice Number</label>
                  <input
                    required
                    className="form-input"
                    value={invForm.invoice_number}
                    onChange={(e) => setInvForm({ ...invForm, invoice_number: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Select Buyer</label>
                  <select
                    className="form-select"
                    value={invForm.customer_id}
                    onChange={(e) =>
                      setInvForm({ ...invForm, customer_id: Number(e.target.value) })
                    }
                  >
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.company_name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group">
                  <label>Issue Date</label>
                  <input
                    type="date"
                    required
                    className="form-input"
                    value={invForm.issue_date}
                    onChange={(e) => setInvForm({ ...invForm, issue_date: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Due Date</label>
                  <input
                    type="date"
                    required
                    className="form-input"
                    value={invForm.due_date}
                    onChange={(e) => setInvForm({ ...invForm, due_date: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Total Invoice Amount (₹)</label>
                <input
                  type="number"
                  step="0.01"
                  required
                  placeholder="e.g. 185000"
                  className="form-input"
                  value={invForm.total_amount}
                  onChange={(e) => setInvForm({ ...invForm, total_amount: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>Goods / Services Description</label>
                <input
                  required
                  placeholder="e.g. Precision Machined Shafts (Batch #52)"
                  className="form-input"
                  value={invForm.description}
                  onChange={(e) => setInvForm({ ...invForm, description: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.55rem',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={invForm.msme_agreement}
                    onChange={(e) =>
                      setInvForm({ ...invForm, msme_agreement: e.target.checked })
                    }
                  />
                  Written Credit Agreement Exists (45-day MSME Statutory Limit; unchecked = 15 days)
                </label>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '0.6rem',
                  marginTop: '1.15rem',
                }}
              >
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => setShowInvoiceModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Create Invoice
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: ADD CUSTOMER */}
      {showCustomerModal && (
        <div className="modal-backdrop" onClick={() => setShowCustomerModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title" style={{ marginBottom: '1.15rem' }}>
              Add Buyer / Customer Account
            </h3>
            <form onSubmit={handleCreateCustomer}>
              <div className="form-grid">
                <div className="form-group">
                  <label>Company Name</label>
                  <input
                    required
                    placeholder="e.g. Tata AutoComp Systems"
                    className="form-input"
                    value={custForm.company_name}
                    onChange={(e) => setCustForm({ ...custForm, company_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Contact Person Name</label>
                  <input
                    required
                    placeholder="e.g. Suresh Kulkarni"
                    className="form-input"
                    value={custForm.name}
                    onChange={(e) => setCustForm({ ...custForm, name: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group">
                  <label>GSTIN</label>
                  <input
                    required
                    placeholder="27AABCT1234F1Z5"
                    className="form-input"
                    value={custForm.gstin}
                    onChange={(e) => setCustForm({ ...custForm, gstin: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Udyam Number (Optional)</label>
                  <input
                    placeholder="UDYAM-MH-26-0011223"
                    className="form-input"
                    value={custForm.udyam_number}
                    onChange={(e) => setCustForm({ ...custForm, udyam_number: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    required
                    placeholder="accounts@company.in"
                    className="form-input"
                    value={custForm.email}
                    onChange={(e) => setCustForm({ ...custForm, email: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Phone (WhatsApp)</label>
                  <input
                    required
                    placeholder="+91 98200 12345"
                    className="form-input"
                    value={custForm.phone}
                    onChange={(e) => setCustForm({ ...custForm, phone: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group">
                  <label>City & State</label>
                  <input
                    required
                    placeholder="Mumbai, Maharashtra"
                    className="form-input"
                    value={custForm.city}
                    onChange={(e) => setCustForm({ ...custForm, city: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Credit Period (Days, max 45 for MSME)</label>
                  <input
                    type="number"
                    required
                    min={1}
                    max={90}
                    className="form-input"
                    value={custForm.credit_period_days}
                    onChange={(e) =>
                      setCustForm({ ...custForm, credit_period_days: Number(e.target.value) })
                    }
                  />
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '0.6rem',
                  marginTop: '1.15rem',
                }}
              >
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => setShowCustomerModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Customer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
