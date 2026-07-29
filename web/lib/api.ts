// Typed client for the Inbox Agent API. Requests go to /api/* which Next
// proxies to the FastAPI backend (see next.config.mjs).

export type EmailSummary = {
  id: string;
  thread_id?: string;
  from_name: string;
  from_addr?: string;
  date: string;
  subject: string;
  snippet: string;
  category: string;
  flagged: string[];
};

export type EmailDetail = EmailSummary & {
  to: string[];
  cc: string[];
  labels: string[];
  body: string;
};

export type CategoryCount = { id: string; count: number };
export type Categories = { total: number; flagged: number; categories: CategoryCount[] };
export type AskHit = {
  id: string;
  from_name: string;
  date: string;
  subject: string;
  snippet: string;
  score: number;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  categories: () => get<Categories>("/categories"),
  emails: (category: string) =>
    get<{ emails: EmailSummary[]; count: number }>(
      `/emails${category && category !== "all" ? `?category=${category}` : ""}`,
    ),
  email: (id: string) => get<EmailDetail>(`/emails/${encodeURIComponent(id)}`),
  ask: async (question: string, k = 5): Promise<{ question: string; hits: AskHit[] }> => {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, k }),
    });
    if (!res.ok) throw new Error(`ask failed: ${res.status}`);
    return res.json();
  },
};

export const CAT_META: Record<string, { label: string; dot: string }> = {
  all: { label: "All mail", dot: "var(--ink-3)" },
  work: { label: "Work", dot: "var(--dot-work)" },
  personal: { label: "Personal", dot: "var(--dot-personal)" },
  newsletter: { label: "Newsletters", dot: "var(--dot-newsletter)" },
  receipt_order: { label: "Receipts", dot: "var(--dot-receipt)" },
  notification: { label: "Notifications", dot: "var(--dot-notification)" },
  spam_phishing: { label: "Spam & phishing", dot: "var(--dot-spam)" },
};

export const CAT_LABEL: Record<string, string> = {
  work: "Work",
  personal: "Personal",
  newsletter: "Newsletter",
  receipt_order: "Receipt / order",
  notification: "Notification",
  spam_phishing: "Spam & phishing",
};

export function dotFor(cat: string): string {
  return CAT_META[cat]?.dot || "var(--ink-3)";
}
export function tintFor(cat: string): string {
  return `color-mix(in srgb, ${dotFor(cat)} 16%, var(--surface))`;
}
export function initials(name: string): string {
  const w = name.trim().split(/\s+/);
  return (w.length >= 2 ? w[0][0] + w[1][0] : name.slice(0, 2)).toUpperCase();
}
