"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import {
  MessageCircle, Globe,
  Database,
  Webhook,
  CheckCircle2,
  Clock3,
  Settings2,
  ArrowUpRight,
  Plug,
  ShieldCheck,
} from "lucide-react";

const integrations = [
  {
    id: "whatsapp",
    name: "WhatsApp Business",
    description: "Connect your WhatsApp Business account to manage customer conversations.",
    category: "Messaging",
    icon: MessageCircle,
  },
  {
    id: "messenger",
    name: "Facebook Messenger",
    description: "Receive and respond to Facebook Messenger customer messages.",
    category: "Messaging",
    icon: Globe,
  },
  {
    id: "lead-ads",
    name: "Facebook Lead Ads",
    description: "Automatically capture leads from your Globe advertising campaigns.",
    category: "Lead capture",
    icon: Globe,
  },
  {
    id: "crm",
    name: "External CRM",
    description: "Connect your existing CRM and synchronize customer information.",
    category: "CRM",
    icon: Database,
  },
  {
    id: "webhook",
    name: "Webhooks",
    description: "Send and receive real-time events between your business applications.",
    category: "Automation",
    icon: Webhook,
  },
];

export default function IntegrationsPage() {
  const [selectedCategory, setSelectedCategory] = useState("All");

  const categories = ["All", "Messaging", "Lead capture", "CRM", "Automation"];
  const visibleIntegrations = integrations.filter(
    (item) => selectedCategory === "All" || item.category === selectedCategory
  );

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">Workspace / Configuration</p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">Integrations</h1>
          </div>
          <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
            Integration center
          </span>
        </header>

        <div className="mx-auto max-w-7xl space-y-7 p-5 sm:p-8">
          <section>
            <h2 className="text-2xl font-bold text-slate-900">Connect your tools</h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
              Bring your communication channels and business applications together
              to create a connected sales workflow.
            </p>
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-blue-50 p-2.5 text-blue-700">
                  <Plug size={20} />
                </div>
                <p className="text-sm font-medium text-slate-500">Available integrations</p>
              </div>
              <p className="mt-4 text-3xl font-bold text-slate-900">{integrations.length}</p>
              <p className="mt-1 text-xs text-slate-400">Supported connection types</p>
            </article>

            <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-green-50 p-2.5 text-green-700">
                  <CheckCircle2 size={20} />
                </div>
                <p className="text-sm font-medium text-slate-500">Connected</p>
              </div>
              <p className="mt-4 text-3xl font-bold text-slate-900">--</p>
              <p className="mt-1 text-xs text-slate-400">Awaiting integration status</p>
            </article>

            <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:col-span-2 xl:col-span-1">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-amber-50 p-2.5 text-amber-700">
                  <Clock3 size={20} />
                </div>
                <p className="text-sm font-medium text-slate-500">Connection status</p>
              </div>
              <p className="mt-4 text-lg font-bold text-slate-900">Not verified</p>
              <p className="mt-1 text-xs text-slate-400">Connect an account to check health</p>
            </article>
          </section>

          <section className="rounded-xl border border-blue-100 bg-blue-50/70 p-5 sm:p-6">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 shrink-0 text-blue-700" size={22} />
              <div>
                <h3 className="font-semibold text-slate-900">Secure account connections</h3>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  Integration credentials should be encrypted and stored securely.
                  Never share access tokens or API secrets in chat, screenshots, or source code.
                </p>
              </div>
            </div>
          </section>

          <section className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">Available integrations</h3>
              <p className="mt-1 text-sm text-slate-500">
                Choose a service to view its connection options.
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

            <div className="grid gap-4 lg:grid-cols-2">
              {visibleIntegrations.map((integration) => {
                const Icon = integration.icon;

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
                            <h4 className="font-semibold text-slate-900">{integration.name}</h4>
                            <p className="mt-1 text-xs text-slate-400">{integration.category}</p>
                          </div>
                        </div>
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-500">
                          Not connected
                        </span>
                      </div>

                      <p className="mt-5 min-h-12 text-sm leading-6 text-slate-500">
                        {integration.description}
                      </p>
                    </div>

                    <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
                      <span className="text-xs text-slate-400">Setup required</span>
                      <button
                        type="button"
                        disabled
                        title="Integration setup requires backend authorization and provider credentials."
                        className="inline-flex cursor-not-allowed items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-400"
                      >
                        <Settings2 size={15} />
                        Configure
                        <ArrowUpRight size={14} />
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}


