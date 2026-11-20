"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Search,
  MessageSquare,
  Send,
  Inbox,
  Clock,
  AlertTriangle,
  Check,
  CheckCheck,
  ArrowUpRight,
  RefreshCw,
  X,
  FileText,
  ShieldAlert,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { useAuth } from "@/providers/auth-provider";
import {
  useConversations,
  useMessages,
  useSendMessage,
} from "@/hooks/use-conversations";
import {
  APPROVED_WHATSAPP_TEMPLATES,
  is24HourWindowActive,
  getWindowRemainingHours,
  type Conversation,
  type Message,
  type WhatsAppTemplate,
} from "@/lib/api/conversations";
import { parseApiError } from "@/lib/api-error";
import { ErrorBanner } from "@/components/shared/error-banner";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { formatTenantDateTime } from "@/lib/format";

const channels = ["All", "WhatsApp", "Messenger"];

export default function ConversationsPage() {
  const { timezone } = useAuth();

  const [activeChannel, setActiveChannel] = useState("All");
  const [search, setSearch] = useState("");
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);

  // Free text message state
  const [messageText, setMessageText] = useState("");

  // Template sending state
  const [selectedTemplate, setSelectedTemplate] = useState<WhatsAppTemplate>(
    APPROVED_WHATSAPP_TEMPLATES[0]
  );
  const [useTemplateMode, setUseTemplateMode] = useState(false);

  // Notices and errors
  const [notice, setNotice] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<{
    title: string;
    message: string;
  } | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    data: conversations = [],
    isLoading: isLoadingConversations,
    refetch: refetchConversations,
  } = useConversations({
    channel: activeChannel === "All" ? undefined : activeChannel.toLowerCase(),
  });

  const selectedConversation = useMemo(() => {
    if (!selectedConversationId) return null;
    return conversations.find((c) => c.id === selectedConversationId) || null;
  }, [conversations, selectedConversationId]);

  // Auto-select first conversation when loaded if none is selected
  useEffect(() => {
    if (!selectedConversationId && conversations.length > 0) {
      setSelectedConversationId(conversations[0].id);
    }
  }, [conversations, selectedConversationId]);

  // Pass undefined (not null/"null") when no conversation is selected so the
  // hook's `enabled: Boolean(conversationId)` guard fires correctly and
  // avoids a spurious GET /conversations/undefined/messages 422 error.
  const {
    data: messages = [],
    isLoading: isLoadingMessages,
    refetch: refetchMessages,
  } = useMessages(selectedConversationId ?? undefined);

  const sendMessageMutation = useSendMessage();

  // Scroll to bottom whenever messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Filter conversations in left panel by search query
  const filteredConversations = useMemo(() => {
    if (!search.trim()) return conversations;
    const q = search.toLowerCase();
    return conversations.filter(
      (c) =>
        (c.lead_name && c.lead_name.toLowerCase().includes(q)) ||
        (c.lead_phone && c.lead_phone.includes(q)) ||
        c.channel.toLowerCase().includes(q)
    );
  }, [conversations, search]);

  // Window state calculations for active conversation
  const isLeadOptedOut = Boolean(selectedConversation?.lead_opted_out);
  const windowActive = selectedConversation
    ? is24HourWindowActive(selectedConversation.last_inbound_at)
    : false;
  const remainingHours = selectedConversation
    ? getWindowRemainingHours(selectedConversation.last_inbound_at)
    : 0;

  // If window is closed, force template mode
  const isTemplateRequired = !windowActive;

  const handleSendTextMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedConversation || !messageText.trim() || isLeadOptedOut) return;

    setErrorBanner(null);

    try {
      await sendMessageMutation.mutateAsync({
        conversation_id: selectedConversation.id,
        text: messageText.trim(),
      });
      setMessageText("");
      setNotice("Message sent.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleSendTemplate = async () => {
    if (!selectedConversation || isLeadOptedOut) return;

    setErrorBanner(null);

    try {
      const recipientName =
        selectedConversation.lead_name ||
        selectedConversation.lead_phone ||
        "Valued Customer";

      await sendMessageMutation.mutateAsync({
        conversation_id: selectedConversation.id,
        template: {
          name: selectedTemplate.name,
          language: selectedTemplate.language,
          params: [recipientName],
        },
      });
      setNotice(`Approved template '${selectedTemplate.label}' sent.`);
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleRefresh = async () => {
    setErrorBanner(null);
    await Promise.all([refetchConversations(), refetchMessages()]);
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        {/* Page Header */}
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">Workspace / Communication</p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              Conversations
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600">
              Timezone: {timezone || "Asia/Dhaka"}
            </span>
            <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
              Unified inbox
            </span>
          </div>
        </header>

        <div className="p-4 sm:p-6">
          {/* Action & Status Row */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">Customer inbox</h2>
              <p className="mt-1 text-sm text-slate-500">
                Engage leads on WhatsApp and Messenger within the 24-hour compliance window.
              </p>
            </div>

            <button
              onClick={() => void handleRefresh()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50"
            >
              <RefreshCw size={14} />
              Refresh
            </button>
          </div>

          {/* Feedback Banners */}
          {errorBanner && (
            <div className="mb-4">
              <ErrorBanner
                title={errorBanner.title}
                message={errorBanner.message}
                onDismiss={() => setErrorBanner(null)}
                onRetry={() => void handleRefresh()}
              />
            </div>
          )}

          {notice && (
            <div className="mb-4 flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-700">
              <span>{notice}</span>
              <button
                onClick={() => setNotice(null)}
                className="text-green-600 hover:text-green-800"
              >
                <X size={15} />
              </button>
            </div>
          )}

          {/* Inbox Split Layout */}
          <section className="grid min-h-[700px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid-cols-[340px_minmax(0,1fr)]">
            {/* Left Panel: Conversation Thread List */}
            <aside className="flex min-w-0 flex-col border-b border-slate-200 lg:border-b-0 lg:border-r">
              <div className="border-b border-slate-100 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-slate-900">Threads</h3>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                    {conversations.length}
                  </span>
                </div>

                {/* Search Input */}
                <div className="relative mt-3">
                  <Search
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    size={16}
                  />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search by name, phone..."
                    className="w-full rounded-xl border border-slate-200 py-2 pl-9 pr-3 text-xs outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                {/* Channel Filter Pills */}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {channels.map((channel) => (
                    <button
                      key={channel}
                      type="button"
                      onClick={() => setActiveChannel(channel)}
                      className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                        activeChannel === channel
                          ? "bg-blue-600 text-white shadow-xs"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {channel}
                    </button>
                  ))}
                </div>
              </div>

              {/* Conversations List View */}
              <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
                {isLoadingConversations ? (
                  <div className="py-12 text-center">
                    <LoadingSpinner size="sm" message="Loading conversations..." />
                  </div>
                ) : filteredConversations.length === 0 ? (
                  <div className="flex flex-col items-center justify-center p-8 text-center">
                    <div className="rounded-full bg-slate-100 p-3 text-slate-400">
                      <Inbox size={24} />
                    </div>
                    <p className="mt-3 text-xs font-semibold text-slate-700">
                      No conversations found
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      Incoming customer messages will appear here.
                    </p>
                  </div>
                ) : (
                  filteredConversations.map((conv: Conversation) => {
                    const isSelected = conv.id === selectedConversationId;
                    const isOptedOut = conv.lead_opted_out;
                    const windowIsOpen = is24HourWindowActive(conv.last_inbound_at);

                    return (
                      <button
                        key={conv.id}
                        onClick={() => setSelectedConversationId(conv.id)}
                        className={`w-full text-left p-3.5 transition flex items-start gap-3 ${
                          isSelected
                            ? "bg-blue-50/80 border-l-4 border-blue-600"
                            : "hover:bg-slate-50"
                        }`}
                      >
                        <div className="relative mt-0.5 shrink-0">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-700">
                            {(conv.lead_name || "L").charAt(0).toUpperCase()}
                          </div>
                          <span
                            className={`absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-white ${
                              isOptedOut
                                ? "bg-red-500"
                                : windowIsOpen
                                ? "bg-green-500"
                                : "bg-amber-400"
                            }`}
                            title={
                              isOptedOut
                                ? "Opted out"
                                : windowIsOpen
                                ? "24h window active"
                                : "Template required"
                            }
                          />
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between">
                            <p className="truncate text-xs font-bold text-slate-900">
                              {conv.lead_name || conv.lead_phone || `Lead ${conv.lead_id.slice(0, 8)}`}
                            </p>
                            <span className="text-[10px] text-slate-400 shrink-0">
                              {conv.last_message_at
                                ? formatTenantDateTime(conv.last_message_at, timezone)
                                : "New"}
                            </span>
                          </div>

                          <div className="mt-1 flex items-center justify-between gap-1 text-[11px]">
                            <span className="capitalize font-medium text-slate-500">
                              {conv.channel}
                            </span>

                            {isOptedOut ? (
                              <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700">
                                Opted out
                              </span>
                            ) : !windowIsOpen ? (
                              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                                Template req
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </aside>

            {/* Right Panel: Chat Thread & Reply Box */}
            <section className="flex min-w-0 flex-col">
              {selectedConversation ? (
                <>
                  {/* Thread Header */}
                  <header className="flex min-h-[73px] items-center justify-between border-b border-slate-100 px-6 py-3 bg-white">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">
                        {(selectedConversation.lead_name || "L").charAt(0).toUpperCase()}
                      </div>

                      <div className="min-w-0">
                        {/* Link to Lead Detail Page */}
                        <div className="flex items-center gap-1.5">
                          <Link
                            href={`/leads/${selectedConversation.lead_id}`}
                            className="group flex items-center gap-1 text-sm font-bold text-slate-900 hover:text-blue-600 transition"
                            title="Open lead details"
                          >
                            <span className="truncate">
                              {selectedConversation.lead_name ||
                                selectedConversation.lead_phone ||
                                "Customer Thread"}
                            </span>
                            <ArrowUpRight
                              size={14}
                              className="text-slate-400 group-hover:text-blue-600"
                            />
                          </Link>
                        </div>

                        <div className="flex items-center gap-2 text-xs text-slate-500">
                          {selectedConversation.lead_phone && (
                            <span>{selectedConversation.lead_phone}</span>
                          )}
                          <span>·</span>
                          <span className="capitalize font-semibold text-blue-700">
                            {selectedConversation.channel}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* 24-Hour Window & Status Badges */}
                    <div className="flex items-center gap-2">
                      {isLeadOptedOut ? (
                        <div className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-bold text-red-700">
                          <ShieldAlert size={14} className="text-red-600" />
                          Opted out
                        </div>
                      ) : windowActive ? (
                        <div className="inline-flex items-center gap-1.5 rounded-full border border-green-200 bg-green-50 px-3 py-1 text-xs font-semibold text-green-700">
                          <Clock size={13} className="text-green-600" />
                          24h window active ({remainingHours}h remaining)
                        </div>
                      ) : (
                        <div className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
                          <AlertTriangle size={13} className="text-amber-600" />
                          24h window closed — Template required
                        </div>
                      )}
                    </div>
                  </header>

                  {/* Messages Feed */}
                  <div className="flex-1 overflow-y-auto p-5 space-y-3 bg-slate-50/40">
                    {isLoadingMessages ? (
                      <div className="py-16 text-center">
                        <LoadingSpinner size="md" message="Loading conversation thread..." />
                      </div>
                    ) : messages.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-16 text-center">
                        <div className="rounded-2xl bg-blue-50 p-4 text-blue-600">
                          <MessageSquare size={28} />
                        </div>
                        <h4 className="mt-3 text-sm font-bold text-slate-800">
                          No messages yet
                        </h4>
                        <p className="mt-1 max-w-sm text-xs text-slate-500">
                          Send a message or an approved WhatsApp template below to initiate communication with this customer.
                        </p>
                      </div>
                    ) : (
                      messages.map((msg: Message) => {
                        const isInbound = msg.direction === "inbound";

                        return (
                          <div
                            key={msg.id}
                            className={`flex flex-col ${
                              isInbound ? "items-start" : "items-end"
                            }`}
                          >
                            <div
                              className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-xs shadow-xs leading-relaxed ${
                                isInbound
                                  ? "bg-white text-slate-800 border border-slate-200/80 rounded-tl-xs"
                                  : "bg-blue-600 text-white rounded-tr-xs"
                              }`}
                            >
                              {/* Customer plain text message */}
                              <p className="whitespace-pre-wrap">{msg.message_text}</p>

                              <div
                                className={`mt-1.5 flex items-center justify-end gap-1.5 text-[10px] ${
                                  isInbound ? "text-slate-400" : "text-blue-100"
                                }`}
                              >
                                <span>{formatTenantDateTime(msg.created_at, timezone)}</span>

                                {!isInbound && (
                                  <span>
                                    {msg.status === "read" ? (
                                      // Double blue ticks — message was read
                                      <CheckCheck size={13} className="text-sky-300" />
                                    ) : msg.status === "delivered" ? (
                                      // Double grey ticks — delivered but not yet read
                                      <CheckCheck size={13} className="text-blue-200/60" />
                                    ) : msg.status === "sent" ? (
                                      <Check size={13} className="text-blue-200" />
                                    ) : msg.status === "failed" ? (
                                      <span className="font-bold text-red-300">
                                        Failed
                                      </span>
                                    ) : (
                                      <span className="opacity-70">Queued</span>
                                    )}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}
                    <div ref={messagesEndRef} />
                  </div>

                  {/* Reply Box Section */}
                  <div className="border-t border-slate-200 bg-white p-4">
                    {/* State 1: Lead is Opted Out */}
                    {isLeadOptedOut ? (
                      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-center">
                        <div className="flex items-center justify-center gap-2 text-xs font-bold text-red-700">
                          <ShieldAlert size={16} />
                          Customer Opted Out
                        </div>
                        <p className="mt-1 text-xs text-red-600">
                          This lead has opted out of receiving messages. In compliance with Meta and privacy policies, communication is disabled.
                        </p>
                      </div>
                    ) : isTemplateRequired || useTemplateMode ? (
                      /* State 2: 24h Window Closed or Template Mode Selected */
                      <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 text-xs font-bold text-amber-900">
                            <FileText size={15} className="text-amber-600" />
                            Approved WhatsApp Template Required
                          </div>

                          {windowActive && (
                            <button
                              type="button"
                              onClick={() => setUseTemplateMode(false)}
                              className="text-xs font-semibold text-blue-600 hover:text-blue-800"
                            >
                              Switch to Free Text
                            </button>
                          )}
                        </div>

                        <p className="text-xs text-amber-800">
                          The 24-hour customer window is closed. Choose an approved WhatsApp template to reach this customer.
                        </p>

                        <div className="space-y-2">
                          <label className="block text-xs font-semibold text-slate-700">
                            Select Template:
                          </label>
                          <select
                            value={selectedTemplate.name}
                            onChange={(e) => {
                              const found = APPROVED_WHATSAPP_TEMPLATES.find(
                                (t) => t.name === e.target.value
                              );
                              if (found) setSelectedTemplate(found);
                            }}
                            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-blue-500"
                          >
                            {APPROVED_WHATSAPP_TEMPLATES.map((tmpl) => (
                              <option key={tmpl.name} value={tmpl.name}>
                                {tmpl.label} ({tmpl.name})
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* Template Preview */}
                        <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
                          <p className="font-semibold text-slate-800">
                            {selectedTemplate.label}
                          </p>
                          <p className="mt-1 text-slate-600 leading-relaxed">
                            {selectedTemplate.description}
                          </p>
                          <p className="mt-2 text-[11px] text-slate-400">
                            Recipient parameter:{" "}
                            <span className="font-semibold text-slate-700">
                              {selectedConversation.lead_name ||
                                selectedConversation.lead_phone ||
                                "Customer"}
                            </span>
                          </p>
                        </div>

                        <div className="flex justify-end pt-1">
                          <button
                            type="button"
                            onClick={() => void handleSendTemplate()}
                            disabled={sendMessageMutation.isPending}
                            className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-green-700 disabled:opacity-50"
                          >
                            <Send size={13} />
                            {sendMessageMutation.isPending
                              ? "Sending Template..."
                              : "Send Approved Template"}
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* State 3: Window Active (Free text reply enabled) */
                      <form onSubmit={handleSendTextMessage} className="space-y-2">
                        <div className="flex items-center justify-between text-xs text-slate-500 px-1">
                          <span className="flex items-center gap-1.5 text-green-700 font-medium">
                            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                            24h reply window open ({remainingHours}h remaining)
                          </span>

                          <button
                            type="button"
                            onClick={() => setUseTemplateMode(true)}
                            className="font-medium text-blue-600 hover:text-blue-800"
                          >
                            Use WhatsApp Template
                          </button>
                        </div>

                        <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 focus-within:border-blue-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100 transition">
                          <input
                            value={messageText}
                            onChange={(e) => setMessageText(e.target.value)}
                            placeholder="Type a message (Shift+Enter for newline)..."
                            className="min-w-0 flex-1 bg-transparent px-2 text-xs outline-none"
                          />

                          <button
                            type="submit"
                            disabled={
                              sendMessageMutation.isPending ||
                              !messageText.trim()
                            }
                            aria-label="Send message"
                            className="rounded-xl bg-blue-600 p-2.5 text-white shadow-xs hover:bg-blue-700 disabled:opacity-40 transition"
                          >
                            <Send size={15} />
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                </>
              ) : (
                /* No Conversation Selected Placeholder */
                <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
                  <div className="rounded-2xl bg-blue-50 p-5 text-blue-600">
                    <MessageSquare size={36} />
                  </div>
                  <h3 className="mt-4 text-base font-bold text-slate-800">
                    Select a conversation
                  </h3>
                  <p className="mt-1 max-w-sm text-xs leading-relaxed text-slate-500">
                    Select a customer thread on the left to read their message history and reply within the 24-hour compliance window.
                  </p>
                </div>
              )}
            </section>
          </section>
        </div>
      </main>
    </div>
  );
}
