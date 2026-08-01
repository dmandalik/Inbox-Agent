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
  labels: string[];
  starred: boolean;
  read: boolean;
  archived: boolean;
};

export type Label = {
  id: string;
  name: string;
  color: string;
  instructions: string;
  count?: number;
};

export type EmailFilters = {
  category?: string;
  sort?: string;
  order?: "asc" | "desc";
  q?: string;
  label?: string;
  starred?: boolean;
  unread?: boolean;
  archived?: boolean;
};

export type EmailDetail = EmailSummary & {
  to: string[];
  cc: string[];
  mail_labels: string[];
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

export type ChatCitation = {
  id: string;
  from_name: string;
  subject: string;
  date: string;
  summary: string;
};
export type ChatResponse = {
  chat_id: string;
  reply: string;
  widened: boolean;
  kind: string;
  citations: ChatCitation[];
};
export type ChatListItem = { id: string; title: string; updated_at: string };
export type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
  citations: ChatCitation[];
  created_at: string;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `${path} failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  categories: () => get<Categories>("/categories"),
  emails: (filters: EmailFilters = {}) => {
    const p = new URLSearchParams();
    if (filters.category && filters.category !== "all" && filters.category !== "flagged") {
      p.set("category", filters.category);
    } else if (filters.category === "flagged") {
      p.set("category", "flagged");
    }
    if (filters.sort) p.set("sort", filters.sort);
    if (filters.order) p.set("order", filters.order);
    if (filters.q) p.set("q", filters.q);
    if (filters.label) p.set("label", filters.label);
    if (filters.starred) p.set("starred", "true");
    if (filters.unread) p.set("unread", "true");
    if (filters.archived) p.set("archived", "true");
    const qs = p.toString();
    return get<{ emails: EmailSummary[]; count: number }>(`/emails${qs ? `?${qs}` : ""}`);
  },
  email: (id: string) => get<EmailDetail>(`/emails/${encodeURIComponent(id)}`),
  setState: async (
    id: string,
    patch: { starred?: boolean; read?: boolean; archived?: boolean },
  ): Promise<EmailSummary> => {
    const res = await fetch(`/api/emails/${encodeURIComponent(id)}/state`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error(`setState failed: ${res.status}`);
    return res.json();
  },
  ask: async (question: string, k = 5): Promise<{ question: string; hits: AskHit[] }> => {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, k }),
    });
    if (!res.ok) throw new Error(`ask failed: ${res.status}`);
    return res.json();
  },
  chat: async (message: string, chatId?: string): Promise<ChatResponse> => {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message, chat_id: chatId }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail || `chat failed: ${res.status}`);
    }
    return res.json();
  },
  labels: () => get<{ labels: Label[] }>("/labels"),
  createLabel: (name: string, color: string, instructions: string): Promise<Label> =>
    send("/labels", "POST", { name, color, instructions }),
  updateLabel: (id: string, patch: Partial<Label>): Promise<Label> =>
    send(`/labels/${encodeURIComponent(id)}`, "PATCH", patch),
  deleteLabel: (id: string): Promise<{ deleted: string }> =>
    send(`/labels/${encodeURIComponent(id)}`, "DELETE"),
  setEmailLabel: (
    id: string,
    labelId: string,
    on: boolean,
  ): Promise<{ id: string; labels: string[] }> =>
    send(`/emails/${encodeURIComponent(id)}/labels`, "POST", { label_id: labelId, on }),
  applyLabels: (): Promise<{ labelled: number; scanned: number }> => send("/labels/apply", "POST"),
  chats: () => get<{ chats: ChatListItem[] }>("/chats"),
  chatHistory: (id: string) =>
    get<{ chat_id: string; messages: ChatHistoryMessage[] }>(`/chats/${encodeURIComponent(id)}`),
  draftReply: async (id: string, guidance?: string): Promise<{ id: string; draft: string }> => {
    const res = await fetch(`/api/emails/${encodeURIComponent(id)}/draft`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ guidance }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail || `draft failed: ${res.status}`);
    }
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
