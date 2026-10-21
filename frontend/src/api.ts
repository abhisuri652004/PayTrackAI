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

const API_BASE = 'http://127.0.0.1:8001/api';

export function formatINR(amount: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: amount % 1 === 0 ? 0 : 2,
  }).format(amount || 0);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let errMsg = `Request failed (${res.status})`;
    try {
      const errBody = await res.json();
      if (errBody.detail) errMsg = errBody.detail;
    } catch {
      // ignore json parse error
    }
    throw new Error(errMsg);
  }
  return res.json();
}

export const api = {
  getDashboard: () => request<DashboardSummary>('/dashboard'),
  getInvoices: () => request<Invoice[]>('/invoices'),
  getInvoiceWorkspace: (invoiceId: number) =>
    request<InvoiceWorkspace>(`/invoices/${invoiceId}/workspace`),
  createInvoice: (data: {
    invoice_number: string;
    customer_id: number;
    issue_date: string;
    due_date: string;
    total_amount: number;
    description: string;
    msme_agreement: boolean;
  }) =>
    request<Invoice>('/invoices', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getCustomers: () => request<Customer[]>('/customers'),
  createCustomer: (data: {
    name: string;
    company_name: string;
    gstin: string;
    udyam_number?: string;
    email: string;
    phone: string;
    city: string;
    credit_period_days: number;
  }) =>
    request<Customer>('/customers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getPayments: () => request<Payment[]>('/payments'),
  recordPayment: (data: {
    invoice_id: number;
    amount: number;
    payment_date: string;
    payment_mode: string;
    reference_number?: string;
    notes?: string;
  }) =>
    request<Payment>('/payments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  generateReminderDraft: (data: {
    invoice_id: number;
    tone: string;
    channel: string;
    log_draft_event?: boolean;
  }) =>
    request<ReminderDraft>('/reminders/draft', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  saveReminderLog: (data: {
    invoice_id: number;
    channel: string;
    tone: string;
    subject: string;
    message_body: string;
    was_edited?: boolean;
  }) =>
    request<ReminderLog>('/reminders/save', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getReminders: () => request<ReminderLog[]>('/reminders'),
  updatePriorityWeights: (weights: PriorityWeightsConfig) =>
    request<{ weights: PriorityWeightsConfig; message: string }>('/priority-config', {
      method: 'PUT',
      body: JSON.stringify(weights),
    }),
  resetPriorityWeights: () =>
    request<{ weights: PriorityWeightsConfig; message: string }>('/priority-config/reset', {
      method: 'POST',
    }),
  resetDemo: () =>
    request<{ message: string }>('/reset-demo', {
      method: 'POST',
    }),
};
