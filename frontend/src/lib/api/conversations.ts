import { apiRequest, createIdempotencyKeyForAction } from "@/lib/api/client";

export type ChannelType = "whatsapp" | "messenger" | "email" | "web";
export type ConversationStatus = "open" | "pending" | "closed";

export interface Conversation {
  id: string;
  lead_id: string;
  channel: ChannelType;
  status: ConversationStatus;
  assigned_user_id: string | null;
  last_message_at: string | null;
  last_inbound_at: string | null;
  created_at: string;
  lead_name?: string | null;
  lead_phone?: string | null;
  lead_opted_out?: boolean | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  provider: string;
  provider_message_id: string | null;
  direction: "inbound" | "outbound";
  message_text: string | null;
  status: "received" | "queued" | "sent" | "delivered" | "read" | "failed";
  error_code: string | null;
  idempotency_key: string | null;
  created_at: string;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
}

export interface WhatsAppTemplate {
  name: string;
  language: string;
  label: string;
  description: string;
}

export const APPROVED_WHATSAPP_TEMPLATES: WhatsAppTemplate[] = [
  {
    name: "demo_follow_up",
    language: "en_US",
    label: "Demo Follow-up",
    description: "Follow up after a demo request or scheduled presentation",
  },
  {
    name: "account_update",
    language: "en_US",
    label: "Account Update",
    description: "Share essential account or inquiry status changes",
  },
  {
    name: "re_engagement_checkin",
    language: "en_US",
    label: "Re-engagement Check-in",
    description: "Reactivate an inactive lead who hasn't replied in >24 hours",
  },
];

export function is24HourWindowActive(lastInboundAt?: string | null): boolean {
  if (!lastInboundAt) return false;
  const inboundTime = new Date(lastInboundAt).getTime();
  if (Number.isNaN(inboundTime)) return false;
  const now = Date.now();
  const diffHours = (now - inboundTime) / (1000 * 60 * 60);
  return diffHours >= 0 && diffHours < 24;
}

export function getWindowRemainingHours(lastInboundAt?: string | null): number {
  if (!lastInboundAt) return 0;
  const inboundTime = new Date(lastInboundAt).getTime();
  if (Number.isNaN(inboundTime)) return 0;
  const now = Date.now();
  const remaining = 24 - (now - inboundTime) / (1000 * 60 * 60);
  return Math.max(0, Math.floor(remaining));
}

export async function getConversations(params?: {
  channel?: string;
  status?: string;
  lead_id?: string;
  limit?: number;
  offset?: number;
}): Promise<Conversation[]> {
  const query = new URLSearchParams();
  if (params?.channel && params.channel !== "All") {
    query.set("channel", params.channel.toLowerCase());
  }
  if (params?.status) query.set("status", params.status);
  if (params?.lead_id) query.set("lead_id", params.lead_id);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));

  const path = query.toString()
    ? `/conversations?${query.toString()}`
    : "/conversations";
  const res = await apiRequest<{ data: Conversation[] }>(path);
  return res.data;
}

export async function getConversation(
  conversationId: string
): Promise<Conversation> {
  const res = await apiRequest<{ data: Conversation }>(
    `/conversations/${conversationId}`
  );
  return res.data;
}

export async function getMessages(
  conversationId: string,
  limit = 100,
  offset = 0
): Promise<Message[]> {
  const res = await apiRequest<{ data: Message[] }>(
    `/conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`
  );
  return res.data;
}

export async function sendMessage(payload: {
  conversation_id: string;
  text?: string;
  template?: {
    name: string;
    language: string;
    params: string[];
  };
}): Promise<Message> {
  const res = await apiRequest<{ data: Message }>("/messages", {
    method: "POST",
    body: payload,
    idempotencyKey: createIdempotencyKeyForAction(),
  });
  return res.data;
}
