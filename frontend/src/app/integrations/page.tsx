
"use client";

import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "@/components/layout/sidebar";
import {
  MessageCircle,
  Globe,
  Database,
  Webhook,
  CheckCircle2,
  Clock3,
  Plug,
  ShieldCheck,
  Settings2,
  ArrowUpRight,
  X,
  LoaderCircle,
  AlertCircle,
  Unplug,
} from "lucide-react";

import {
  listIntegrations,
  connectIntegration,
  disconnectIntegration,
  type IntegrationProvider,
} from "@/lib/api/integrations";

const integrations = [
  {
    id: "whatsapp",
    name: "WhatsApp Business",
    description:
      "Connect your WhatsApp Business account to manage customer conversations.",
    category: "Messaging",
    icon: MessageCircle,
    provider: "whatsapp" as const,
    available: true,
  },
  {
    id: "meta",
    name: "Meta Business",
    description:
      "Connect a Facebook Page for Messenger messaging and Lead Ads subscriptions.",
    category: "Messaging",
    icon: Globe,
    provider: "meta" as const,
    available: true,
  },
  {
    id: "crm",
    name: "External CRM",
    description:
      "Connect your existing CRM and synchronize customer information.",
    category: "CRM",
    icon: Database,
    available: false,
  },
  {
    id: "webhook",
    name: "Webhooks",
    description:
      "Configure real-time events between your business applications.",
    category: "Automation",
    icon: Webhook,
    available: false,
  },
];

const categories = ["All", "Messaging", "CRM", "Automation"];

export default function IntegrationsPage() {
  const queryClient = useQueryClient();

  const [selectedCategory, setSelectedCategory] = useState("All");
  const [selectedProvider, setSelectedProvider] =
    useState<IntegrationProvider | null>(null);

  const [accountId, setAccountId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [wabaId, setWabaId] = useState("");

  const integrationsQuery = useQuery({
    queryKey: ["integrations"],
    queryFn: listIntegrations,
    retry: false,
  });

  const connectMutation = useMutation({
    mutationFn: ({
      provider,
      providerAccountId,
      token,
      businessAccountId,
    }: {
      provider: IntegrationProvider;
      providerAccountId: string;
      token: string;
      businessAccountId: string;
    }) =>
      connectIntegration(provider, {
        provider_account_id: providerAccountId,
        access_token: token,
        ...(provider === "whatsapp" && businessAccountId
          ? { waba_id: businessAccountId }
          : {}),
      }),
    onSuccess: async () => {
      setAccessToken("");
      setAccountId("");
      setWabaId("");
      setSelectedProvider(null);
      await queryClient.invalidateQueries({
        queryKey: ["integrations"],
      });
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: disconnectIntegration,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["integrations"],
      });
    },
  });

  const connectedIntegrations = integrationsQuery.data ?? [];

  const activeCount = connectedIntegrations.filter(
    (item) => item.connected && item.status === "active",
  ).length;

  const visibleIntegrations = integrations.filter(
    (item) =>
      selectedCategory === "All" || item.category === selectedCategory,
  );

  function openConnect(provider: IntegrationProvider) {
    setAccountId("");
    setAccessToken("");
    setWabaId("");
    connectMutation.reset();
    setSelectedProvider(provider);
  }

  function closeConnect() {
    if (connectMutation.isPending) return;

    setSelectedProvider(null);
    setAccountId("");
    setAccessToken("");
    setWabaId("");
    connectMutation.reset();
  }

  function handleConnect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedProvider || !accountId.trim() || !accessToken.trim()) {
      return;
    }

    connectMutation.mutate({
      provider: selectedProvider,
      providerAccountId: accountId.trim(),
      token: accessToken,
      businessAccountId: wabaId.trim(),
    });
  }

  function getConnection(provider: string) {
    return connectedIntegrations.filter(
      (item) => item.provider === provider,
    );
  }

  function getStatus(provider: string) {
    const connections = getConnection(provider);

    if (connections.some((item) => item.status === "active")) {
      return "Connected";
    }

    if (connections.some((item) => item.status === "error")) {
      return "Error";
    }

    if (connections.some((item) => item.status === "disabled")) {
      return "Disconnected";
    }

    return "Not connected";
  }

  const selectedIntegration = integrations.find(
    (item) => item.provider === selectedProvider,
  );

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">
              Workspace / Configuration
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              Integrations
            </h1>
          </div>

          <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
            Integration center
          </span>
        </header>

        <div className="mx-auto max-w-7xl space-y-7 p-5 sm:p-8">
          <section>
            <h2 className="text-2xl font-bold text-slate-900">
              Connect your tools
            </h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
              Bring your communication channels and business applications
              together to create a connected sales workflow.
            </p>
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-blue-50 p-2.5 text-blue-700">
                  <Plug size={20} />
                </div>
                <p className="text-sm font-medium text-slate-500">
                  Available integrations
                </p>
              </div>
              <p className="mt-4 text-3xl font-bold text-slate-900">
                {integrations.filter((item) => item.available).length}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Currently supported by the backend
              </p>
            </article>

            <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-green-50 p-2.5 text-green-700">
                  <CheckCircle2 size={20} />
                </div>
                <p className="text-sm font-medium text-slate-500">
                  Connected
                </p>
              </div>
              <p className="mt-4 text-3xl font-bold text-slate-900">
                {integrationsQuery.isLoading ? "..." : activeCount}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Active connected accounts
              </p>
            </article>

            <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:col-span-2 xl:col-span-1">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-amber-50 p-2.5 text-amber-700">
                  <Clock3 size={20} />
                </div>
                <p className="text-sm font-medium text-slate-500">
                  Connection status
                </p>
              </div>
              <p className="mt-4 text-lg font-bold text-slate-900">
                {integrationsQuery.isLoading
                  ? "Checking..."
                  : integrationsQuery.isError
                    ? "Unavailable"
                    : activeCount > 0
                      ? "Accounts connected"
                      : "Awaiting setup"}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Based on backend connection records
              </p>
            </article>
          </section>

          {integrationsQuery.isError && (
            <div
              role="alert"
              className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
            >
              <AlertCircle size={19} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold">
                  Could not load integrations
                </p>
                <p className="mt-1">
                  {integrationsQuery.error instanceof Error
                    ? integrationsQuery.error.message
                    : "An unexpected error occurred."}
                </p>
                <button
                  type="button"
                  onClick={() => integrationsQuery.refetch()}
                  className="mt-2 font-semibold underline"
                >
                  Try again
                </button>
              </div>
            </div>
          )}

          <section className="rounded-xl border border-blue-100 bg-blue-50/70 p-5 sm:p-6">
            <div className="flex items-start gap-3">
              <ShieldCheck
                className="mt-0.5 shrink-0 text-blue-700"
                size={22}
              />
              <div>
                <h3 className="font-semibold text-slate-900">
                  Secure account connections
                </h3>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  Integration credentials are encrypted by the backend.
                  Never share access tokens or API secrets in screenshots,
                  chat messages, or source code.
                </p>
              </div>
            </div>
          </section>

          <section className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">
                Available integrations
              </h3>
              <p className="mt-1 text-sm text-slate-500">
                Connect supported services or explore integrations planned
                for future development.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {categories.map((category) => (
                <button
                  key={category}
                  type="button"
                  onClick={() => setSelectedCategory(category)}
                  className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                    selectedCategory === category
                      ? "bg-blue-600 text-white"
                      : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {category}
                </button>
              ))}
            </div>

            {integrationsQuery.isLoading ? (
              <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white p-10 text-sm text-slate-500">
                <LoaderCircle size={19} className="animate-spin" />
                Loading your integrations...
              </div>
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                {visibleIntegrations.map((integration) => {
                  const Icon = integration.icon;
                  const connections = integration.provider
                    ? getConnection(integration.provider)
                    : [];
                  const status = integration.provider
                    ? getStatus(integration.provider)
                    : "Coming soon";

                  return (
                    <article
                      key={integration.id}
                      className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-blue-200 hover:shadow-md sm:p-6"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <div className="rounded-xl bg-slate-100 p-3 text-slate-700">
                              <Icon size={23} />
                            </div>
                            <div>
                              <h4 className="font-semibold text-slate-900">
                                {integration.name}
                              </h4>
                              <p className="mt-1 text-xs text-slate-400">
                                {integration.category}
                              </p>
                            </div>
                          </div>

                          <span
                            className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                              status === "Connected"
                                ? "bg-green-50 text-green-700"
                                : status === "Error"
                                  ? "bg-red-50 text-red-700"
                                  : "bg-slate-100 text-slate-500"
                            }`}
                          >
                            {status}
                          </span>
                        </div>

                        <p className="mt-5 min-h-12 text-sm leading-6 text-slate-500">
                          {integration.description}
                        </p>

                        {connections.length > 0 && (
                          <div className="mt-4 space-y-2">
                            {connections.map((connection) => (
                              <div
                                key={connection.id}
                                className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-3"
                              >
                                <div className="min-w-0">
                                  <p className="break-all text-xs font-medium text-slate-700">
                                    Account: {connection.provider_account_id}
                                  </p>
                                  <p className="mt-1 text-xs text-slate-400">
                                    {connection.status}
                                  </p>
                                </div>

                                <button
                                  type="button"
                                  disabled={disconnectMutation.isPending}
                                  onClick={() =>
                                    disconnectMutation.mutate(connection.id)
                                  }
                                  className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-2 text-xs font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-50"
                                >
                                  {disconnectMutation.isPending ? (
                                    <LoaderCircle
                                      size={14}
                                      className="animate-spin"
                                    />
                                  ) : (
                                    <Unplug size={14} />
                                  )}
                                  Disconnect
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
                        <span className="text-xs text-slate-400">
                          {integration.available
                            ? "Backend connection supported"
                            : "Planned integration"}
                        </span>

                        {integration.available && integration.provider ? (
                          <button
                            type="button"
                            onClick={() =>
                              openConnect(integration.provider!)
                            }
                            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
                          >
                            <Settings2 size={15} />
                            Connect account
                            <ArrowUpRight size={14} />
                          </button>
                        ) : (
                          <span className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-400">
                            Coming soon
                          </span>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          {disconnectMutation.isError && (
            <p role="alert" className="text-sm text-red-600">
              Could not disconnect the account:{" "}
              {disconnectMutation.error instanceof Error
                ? disconnectMutation.error.message
                : "Unknown error"}
            </p>
          )}

          {selectedProvider && selectedIntegration && (
            <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/50 p-4">
              <section
                role="dialog"
                aria-modal="true"
                aria-labelledby="connect-title"
                className="my-auto w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h2
                      id="connect-title"
                      className="text-xl font-bold text-slate-900"
                    >
                      Connect {selectedIntegration.name}
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Enter your provider account details.
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={closeConnect}
                    disabled={connectMutation.isPending}
                    aria-label="Close dialog"
                    className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
                  >
                    <X size={20} />
                  </button>
                </div>

                <form onSubmit={handleConnect} className="mt-6 space-y-4">
                  <div>
                    <label
                      htmlFor="provider-account-id"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      {selectedProvider === "meta"
                        ? "Facebook Page ID"
                        : "WhatsApp Phone Number ID"}
                    </label>
                    <input
                      id="provider-account-id"
                      value={accountId}
                      onChange={(event) => setAccountId(event.target.value)}
                      required
                      maxLength={128}
                      autoComplete="off"
                      placeholder="Enter provider account ID"
                      className="w-full rounded-lg border border-slate-300 px-4 py-3 text-sm text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                    />
                  </div>

                  {selectedProvider === "whatsapp" && (
                    <div>
                      <label
                        htmlFor="waba-id"
                        className="mb-2 block text-sm font-medium text-slate-700"
                      >
                        WhatsApp Business Account ID (optional)
                      </label>
                      <input
                        id="waba-id"
                        value={wabaId}
                        onChange={(event) => setWabaId(event.target.value)}
                        maxLength={128}
                        autoComplete="off"
                        placeholder="Enter WABA ID"
                        className="w-full rounded-lg border border-slate-300 px-4 py-3 text-sm text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>
                  )}

                  <div>
                    <label
                      htmlFor="access-token"
                      className="mb-2 block text-sm font-medium text-slate-700"
                    >
                      Access token
                    </label>
                    <input
                      id="access-token"
                      type="password"
                      value={accessToken}
                      onChange={(event) => setAccessToken(event.target.value)}
                      required
                      autoComplete="new-password"
                      placeholder="Paste your provider access token"
                      className="w-full rounded-lg border border-slate-300 px-4 py-3 text-sm text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                    />
                    <p className="mt-2 text-xs leading-5 text-slate-400">
                      Your token is sent directly to the backend for
                      validation and encrypted storage. Never share it with
                      anyone.
                    </p>
                  </div>

                  {connectMutation.isError && (
                    <div
                      role="alert"
                      className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
                    >
                      {connectMutation.error instanceof Error
                        ? connectMutation.error.message
                        : "Could not connect this account."}
                    </div>
                  )}

                  <div className="flex justify-end gap-3 border-t border-slate-100 pt-4">
                    <button
                      type="button"
                      onClick={closeConnect}
                      disabled={connectMutation.isPending}
                      className="rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Cancel
                    </button>

                    <button
                      type="submit"
                      disabled={
                        connectMutation.isPending ||
                        !accountId.trim() ||
                        !accessToken.trim()
                      }
                      className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {connectMutation.isPending && (
                        <LoaderCircle size={16} className="animate-spin" />
                      )}
                      {connectMutation.isPending
                        ? "Connecting..."
                        : "Connect account"}
                    </button>
                  </div>
                </form>
              </section>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

