"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { RouteGuard } from "@/components/auth/route-guard";
import { NotificationBell } from "@/components/layout/notification-bell";
import { ErrorBanner } from "@/components/shared/error-banner";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { RefreshButton } from "@/components/shared/refresh-button";
import { parseApiError } from "@/lib/api-error";
import {
  useIntegrations,
  useConnectIntegration,
  useDisconnectIntegration,
  useLeadForm,
} from "@/hooks/use-integrations";
import type {
  IntegrationItem,
  IntegrationProvider,
} from "@/lib/api/integrations";
import {
  MessageCircle,
  Globe,
  Plug,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Copy,
  Check,
  Eye,
  X,
  KeyRound,
  ShieldCheck,
  Layers,
  Settings2,
  Code2,
} from "lucide-react";

export default function IntegrationsPage() {
  const { data: integrations, isLoading, error, refetch, isFetching } = useIntegrations();
  const { data: leadForm } = useLeadForm();
  const connectMutation = useConnectIntegration();
  const disconnectMutation = useDisconnectIntegration();

  // Modals state
  const [connectProvider, setConnectProvider] =
    useState<IntegrationProvider | null>(null);
  const [disconnectItem, setDisconnectItem] = useState<IntegrationItem | null>(
    null
  );
  const [showEmbedModal, setShowEmbedModal] = useState(false);
  const [copiedEmbed, setCopiedEmbed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);

  // Connect form fields
  const [accountId, setAccountId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [wabaId, setWabaId] = useState("");

  const parsedError = error ? parseApiError(error) : null;

  // Active integration lookups
  const whatsappIntegration = integrations?.find(
    (item) => item.provider === "whatsapp" && item.status === "active"
  );
  const metaIntegration = integrations?.find(
    (item) => item.provider === "meta" && item.status === "active"
  );

  const activeCount =
    integrations?.filter((i) => i.status === "active").length ?? 0;

  const openConnectModal = (provider: IntegrationProvider) => {
    setConnectProvider(provider);
    setAccountId("");
    setAccessToken("");
    setWabaId("");
    setModalError(null);
  };

  const closeConnectModal = () => {
    setConnectProvider(null);
    setAccountId("");
    setAccessToken("");
    setWabaId("");
    setModalError(null);
  };

  const handleConnectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!connectProvider) return;

    if (!accountId.trim()) {
      setModalError("Provider Account / Page ID is required.");
      return;
    }
    if (!accessToken.trim()) {
      setModalError("Access token is required.");
      return;
    }

    if (connectProvider === "meta" && !/^\d+$/.test(accountId.trim())) {
      setModalError("Meta Page ID must be numeric.");
      return;
    }

    try {
      await connectMutation.mutateAsync({
        provider: connectProvider,
        data: {
          provider_account_id: accountId.trim(),
          access_token: accessToken.trim(),
          waba_id: wabaId.trim() || undefined,
        },
      });

      const providerLabel =
        connectProvider === "whatsapp" ? "WhatsApp Business" : "Meta (Facebook)";
      setNotice(`Successfully connected ${providerLabel}.`);
      closeConnectModal();
    } catch (err) {
      const parsed = parseApiError(err);
      setModalError(parsed.message);
    }
  };

  const handleDisconnect = async () => {
    if (!disconnectItem) return;
    try {
      await disconnectMutation.mutateAsync(disconnectItem.id);
      const providerLabel =
        disconnectItem.provider === "whatsapp"
          ? "WhatsApp Business"
          : "Meta (Facebook)";
      setNotice(`Disconnected ${providerLabel}.`);
      setDisconnectItem(null);
    } catch (err) {
      const parsed = parseApiError(err);
      setNotice(`Failed to disconnect: ${parsed.message}`);
      setDisconnectItem(null);
    }
  };

  const handleCopyEmbed = () => {
    if (!leadForm?.embed_code) return;
    navigator.clipboard.writeText(leadForm.embed_code);
    setCopiedEmbed(true);
    setTimeout(() => setCopiedEmbed(false), 2500);
  };

  return (
    <RouteGuard allowedRoles={["admin"]}>
      <div className="flex min-h-screen bg-slate-50">
        <Sidebar />

        <main className="min-w-0 flex-1">
          {/* Header */}
          <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
            <div>
              <p className="text-sm text-slate-500">Workspace / Configuration</p>
              <h1 className="mt-1 text-xl font-bold text-slate-900">
                Channel Integrations
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <RefreshButton
                onRefresh={() => refetch()}
                isRefreshing={isFetching}
              />
              <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700">
                Admin Area
              </span>
              <NotificationBell placement="header" />
            </div>
          </header>

          <div className="mx-auto max-w-7xl space-y-7 p-5 sm:p-8">
            {/* Notice / Feedback */}
            {notice && (
              <div className="flex items-center justify-between rounded-xl border border-green-200 bg-green-50 p-4 text-sm font-medium text-green-800">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={18} className="text-green-600" />
                  <span>{notice}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setNotice(null)}
                  className="text-green-600 hover:text-green-900"
                >
                  <X size={16} />
                </button>
              </div>
            )}

            {parsedError && (
              <ErrorBanner
                title={parsedError.title}
                message={parsedError.message}
              />
            )}

            {/* Page Intro */}
            <section>
              <h2 className="text-2xl font-bold text-slate-900">
                Connect customer communication channels
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">
                Connect your WhatsApp Business API, Meta Pages, and website lead
                forms to capture inbound inquiries, run AI qualification, and
                send automated follow-ups.
              </p>
            </section>

            {/* Metric Summary Cards */}
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-blue-50 p-2.5 text-blue-700">
                    <Plug size={20} />
                  </div>
                  <p className="text-sm font-medium text-slate-500">
                    Active channels
                  </p>
                </div>
                <p className="mt-4 text-3xl font-bold text-slate-900">
                  {isLoading ? "--" : activeCount}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  Connected messaging channels
                </p>
              </article>

              <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-green-50 p-2.5 text-green-700">
                    <CheckCircle2 size={20} />
                  </div>
                  <p className="text-sm font-medium text-slate-500">
                    Inbound webhooks
                  </p>
                </div>
                <p className="mt-4 text-xl font-bold text-slate-900">
                  HMAC Verified
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  SHA-256 signature enforcement active
                </p>
              </article>

              <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:col-span-2 xl:col-span-1">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-indigo-50 p-2.5 text-indigo-700">
                    <Code2 size={20} />
                  </div>
                  <p className="text-sm font-medium text-slate-500">
                    Public lead form
                  </p>
                </div>
                <p className="mt-4 text-lg font-bold text-slate-900">
                  {leadForm ? "Ready to embed" : "Loading..."}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  Spam protected with honeypot validation
                </p>
              </article>
            </section>

            {/* Security Guarantee Banner */}
            <section className="rounded-xl border border-blue-100 bg-blue-50/70 p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 shrink-0 text-blue-700" size={22} />
                <div>
                  <h3 className="font-semibold text-slate-900">
                    Write-only credential encryption
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">
                    All provider tokens and API keys are strictly write-only. They
                    are encrypted with AES-256-GCM using tenant-specific
                    associated data, never logged in plaintext, and never returned
                    in API responses or stored in browser state.
                  </p>
                </div>
              </div>
            </section>

            {/* Integrations Grid */}
            <section className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">
                  Configured integrations
                </h3>
                <p className="mt-1 text-sm text-slate-500">
                  Manage active connections and credentials for your tenant.
                </p>
              </div>

              {isLoading ? (
                <div className="flex justify-center py-12">
                  <LoadingSpinner message="Loading integrations..." />
                </div>
              ) : (
                <div className="grid gap-6 lg:grid-cols-2">
                  {/* WhatsApp Business Card */}
                  <article className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                    <div>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="rounded-xl bg-emerald-50 p-3 text-emerald-600">
                            <MessageCircle size={24} />
                          </div>
                          <div>
                            <h4 className="font-semibold text-slate-900">
                              WhatsApp Business
                            </h4>
                            <p className="text-xs text-slate-400">
                              Messaging & Conversational Follow-ups
                            </p>
                          </div>
                        </div>

                        {whatsappIntegration ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                            <CheckCircle2 size={13} /> Active
                          </span>
                        ) : (
                          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
                            Not connected
                          </span>
                        )}
                      </div>

                      <p className="mt-4 text-sm leading-6 text-slate-600">
                        Connect your Meta Cloud WhatsApp API to receive inbound customer
                        messages, send 24-hour compliance replies, and trigger AI follow-up tasks.
                      </p>

                      {whatsappIntegration && (
                        <div className="mt-4 space-y-1.5 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                          <div className="flex justify-between">
                            <span className="font-medium text-slate-500">
                              Phone Number ID:
                            </span>
                            <span className="font-mono text-slate-800">
                              {whatsappIntegration.provider_account_id}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="font-medium text-slate-500">Status:</span>
                            <span className="capitalize text-emerald-700">
                              {whatsappIntegration.status}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="font-medium text-slate-500">Connected on:</span>
                            <span>
                              {new Date(
                                whatsappIntegration.created_at
                              ).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4">
                      {whatsappIntegration ? (
                        <>
                          <button
                            type="button"
                            onClick={() => openConnectModal("whatsapp")}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            <Settings2 size={14} /> Update Token
                          </button>
                          <button
                            type="button"
                            onClick={() => setDisconnectItem(whatsappIntegration)}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-50"
                          >
                            <Trash2 size={14} /> Disconnect
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => openConnectModal("whatsapp")}
                          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 transition"
                        >
                          <KeyRound size={16} /> Connect WhatsApp
                        </button>
                      )}
                    </div>
                  </article>

                  {/* Meta (Facebook Page & Lead Ads) Card */}
                  <article className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                    <div>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="rounded-xl bg-blue-50 p-3 text-blue-600">
                            <Globe size={24} />
                          </div>
                          <div>
                            <h4 className="font-semibold text-slate-900">
                              Meta (Facebook Lead Ads)
                            </h4>
                            <p className="text-xs text-slate-400">
                              Lead Capture & Messenger
                            </p>
                          </div>
                        </div>

                        {metaIntegration ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
                            <CheckCircle2 size={13} /> Active
                          </span>
                        ) : (
                          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
                            Not connected
                          </span>
                        )}
                      </div>

                      <p className="mt-4 text-sm leading-6 text-slate-600">
                        Automatically subscribe your Facebook Pages to capture Instant Form
                        leads and Messenger messages. Subscribes page leadgen webhooks automatically.
                      </p>

                      {metaIntegration && (
                        <div className="mt-4 space-y-1.5 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                          <div className="flex justify-between">
                            <span className="font-medium text-slate-500">Page ID:</span>
                            <span className="font-mono text-slate-800">
                              {metaIntegration.provider_account_id}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="font-medium text-slate-500">Status:</span>
                            <span className="capitalize text-blue-700">
                              {metaIntegration.status}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="font-medium text-slate-500">Connected on:</span>
                            <span>
                              {new Date(
                                metaIntegration.created_at
                              ).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4">
                      {metaIntegration ? (
                        <>
                          <button
                            type="button"
                            onClick={() => openConnectModal("meta")}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            <Settings2 size={14} /> Update Token
                          </button>
                          <button
                            type="button"
                            onClick={() => setDisconnectItem(metaIntegration)}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-50"
                          >
                            <Trash2 size={14} /> Disconnect
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => openConnectModal("meta")}
                          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition"
                        >
                          <KeyRound size={16} /> Connect Meta Page
                        </button>
                      )}
                    </div>
                  </article>

                  {/* Public Lead Form Embed Card */}
                  <article className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
                    <div>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="rounded-xl bg-violet-50 p-3 text-violet-600">
                            <Layers size={24} />
                          </div>
                          <div>
                            <h4 className="font-semibold text-slate-900">
                              Website Lead Capture Form
                            </h4>
                            <p className="text-xs text-slate-400">
                              Direct Web Ingestion Endpoint
                            </p>
                          </div>
                        </div>
                        <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-700">
                          Ready to Embed
                        </span>
                      </div>

                      <p className="mt-4 text-sm leading-6 text-slate-600">
                        Embed your company lead form on any static website, WordPress, or
                        custom landing page. Inquiries submit directly into the CRM, trigger
                        AI qualification, and automatically schedule initial follow-up tasks.
                      </p>

                      {leadForm && (
                        <div className="mt-4 rounded-lg bg-slate-900 p-4 font-mono text-xs text-slate-200">
                          <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-slate-400">
                            <span>Endpoint URL</span>
                            <span className="text-[11px] text-emerald-400">
                              Active (Honeypot Enabled)
                            </span>
                          </div>
                          <p className="mt-2 text-blue-300 break-all">
                            {leadForm.endpoint_url}
                          </p>
                        </div>
                      )}
                    </div>

                    <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                      <div className="text-xs text-slate-500">
                        Includes anti-spam honeypot & UTF-8 name/phone sanitization
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setShowEmbedModal(true)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          <Eye size={14} /> Preview Form Code
                        </button>
                        <button
                          type="button"
                          onClick={handleCopyEmbed}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-blue-700 transition"
                        >
                          {copiedEmbed ? <Check size={14} /> : <Copy size={14} />}
                          {copiedEmbed ? "Copied to Clipboard!" : "Copy Embed Code"}
                        </button>
                      </div>
                    </div>
                  </article>
                </div>
              )}
            </section>
          </div>
        </main>

        {/* Connect Modal */}
        {connectProvider && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm animate-in fade-in duration-100">
            <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl ring-1 ring-black/5 sm:p-7">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div className="flex items-center gap-2.5">
                  <div
                    className={`rounded-lg p-2 ${
                      connectProvider === "whatsapp"
                        ? "bg-emerald-50 text-emerald-600"
                        : "bg-blue-50 text-blue-600"
                    }`}
                  >
                    <KeyRound size={20} />
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-900">
                      {connectProvider === "whatsapp"
                        ? "Connect WhatsApp Business"
                        : "Connect Meta Page"}
                    </h3>
                    <p className="text-xs text-slate-400">
                      Write-only credentials are encrypted before storage.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={closeConnectModal}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                >
                  <X size={20} />
                </button>
              </div>

              {modalError && (
                <div className="mt-4 rounded-lg bg-red-50 p-3 text-xs text-red-700">
                  {modalError}
                </div>
              )}

              <form onSubmit={handleConnectSubmit} className="mt-5 space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
                    {connectProvider === "whatsapp"
                      ? "Phone Number ID *"
                      : "Facebook Page ID (Numeric) *"}
                  </label>
                  <input
                    type="text"
                    required
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                    placeholder={
                      connectProvider === "whatsapp"
                        ? "e.g. 109283746501928"
                        : "e.g. 102938475610293"
                    }
                    className="mt-1.5 w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  <p className="mt-1 text-[11px] text-slate-400">
                    {connectProvider === "whatsapp"
                      ? "Find in Meta App Dashboard > WhatsApp > API Setup."
                      : "Must be a numeric Facebook Page ID."}
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Access Token (Write-Only) *
                  </label>
                  <input
                    type="password"
                    required
                    value={accessToken}
                    onChange={(e) => setAccessToken(e.target.value)}
                    placeholder="Paste permanent system user or page access token"
                    className="mt-1.5 w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm font-mono focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  <p className="mt-1 text-[11px] text-slate-400">
                    Token is transmitted securely and encrypted with AES-256-GCM.
                    Never displayed again.
                  </p>
                </div>

                {connectProvider === "whatsapp" && (
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
                      WhatsApp Business Account (WABA) ID (Optional)
                    </label>
                    <input
                      type="text"
                      value={wabaId}
                      onChange={(e) => setWabaId(e.target.value)}
                      placeholder="e.g. 918273645019283"
                      className="mt-1.5 w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                )}

                <div className="mt-6 flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
                  <button
                    type="button"
                    onClick={closeConnectModal}
                    className="rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={connectMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
                  >
                    {connectMutation.isPending ? "Connecting..." : "Save & Verify"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Disconnect Confirmation Modal */}
        {disconnectItem && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm animate-in fade-in duration-100">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl ring-1 ring-black/5">
              <div className="flex items-center gap-3 text-red-600">
                <div className="rounded-full bg-red-100 p-2.5">
                  <AlertCircle size={22} />
                </div>
                <h3 className="font-bold text-slate-900">
                  Disconnect Integration
                </h3>
              </div>

              <p className="mt-3 text-sm leading-6 text-slate-600">
                Are you sure you want to disconnect this channel?
                Inbound messages and leads from this account will no longer be
                processed.
              </p>

              <div className="mt-6 flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
                <button
                  type="button"
                  onClick={() => setDisconnectItem(null)}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDisconnect}
                  disabled={disconnectMutation.isPending}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-700 disabled:opacity-50"
                >
                  {disconnectMutation.isPending
                    ? "Disconnecting..."
                    : "Confirm Disconnect"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Lead Form Embed Code Modal */}
        {showEmbedModal && leadForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm animate-in fade-in duration-100">
            <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl ring-1 ring-black/5 sm:p-7">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div>
                  <h3 className="font-bold text-slate-900">
                    Lead Form HTML Embed Code
                  </h3>
                  <p className="text-xs text-slate-400">
                    Paste this snippet into your website template.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowEmbedModal(false)}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="mt-4">
                <pre className="max-h-80 overflow-y-auto rounded-lg bg-slate-950 p-4 font-mono text-xs leading-5 text-emerald-400">
                  {leadForm.embed_code}
                </pre>
              </div>

              <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
                <p className="text-xs text-slate-500">
                  Target: <span className="font-mono">{leadForm.endpoint_url}</span>
                </p>
                <button
                  type="button"
                  onClick={handleCopyEmbed}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-blue-700 transition"
                >
                  {copiedEmbed ? <Check size={14} /> : <Copy size={14} />}
                  {copiedEmbed ? "Copied!" : "Copy Code"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </RouteGuard>
  );
}
