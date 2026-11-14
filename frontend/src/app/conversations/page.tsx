"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import {
  Search,
  MessageSquare,
  Send,
  Paperclip,
  MoreVertical,
  Phone,
  Video,
  User,
  Inbox,
  Filter,
} from "lucide-react";

const channels = ["All", "WhatsApp", "Messenger", "Facebook"];

export default function ConversationsPage() {
  const [activeChannel, setActiveChannel] = useState("All");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
          <div>
            <p className="text-sm text-slate-500">Workspace / Communication</p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">Conversations</h1>
          </div>
          <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
            Unified inbox
          </span>
        </header>

        <div className="p-4 sm:p-6">
          <div className="mb-5">
            <h2 className="text-2xl font-bold text-slate-900">Customer inbox</h2>
            <p className="mt-1 text-sm text-slate-500">
              Manage customer conversations across your connected channels.
            </p>
          </div>

          <section className="grid min-h-[650px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:grid-cols-[320px_minmax(0,1fr)]">
            <aside className="flex min-w-0 flex-col border-b border-slate-200 lg:border-b-0 lg:border-r">
              <div className="border-b border-slate-100 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-slate-900">Inbox</h3>
                  <button
                    type="button"
                    aria-label="Filter conversations"
                    className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
                  >
                    <Filter size={18} />
                  </button>
                </div>

                <div className="relative mt-4">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search conversations..."
                    className="w-full rounded-lg border border-slate-200 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {channels.map((channel) => (
                    <button
                      key={channel}
                      type="button"
                      onClick={() => setActiveChannel(channel)}
                      className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                        activeChannel === channel
                          ? "bg-blue-600 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {channel}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
                <div className="rounded-full bg-slate-100 p-4">
                  <Inbox size={27} className="text-slate-400" />
                </div>
                <h3 className="mt-4 text-sm font-semibold text-slate-700">
                  No conversations yet
                </h3>
                <p className="mt-1 max-w-[230px] text-xs leading-5 text-slate-400">
                  Customer messages will appear here when a communication channel is connected.
                </p>
              </div>
            </aside>

            <section className="flex min-w-0 flex-col">
              <header className="flex min-h-[73px] items-center justify-between border-b border-slate-100 px-5">
                <div className="flex items-center gap-3">
                  <div className="rounded-full bg-slate-100 p-2.5">
                    <User size={19} className="text-slate-500" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">Select a conversation</p>
                    <p className="mt-0.5 text-xs text-slate-400">Customer details will appear here</p>
                  </div>
                </div>

                <div className="flex items-center gap-1 text-slate-400">
                  <button type="button" disabled aria-label="Call customer" className="rounded-lg p-2 opacity-40">
                    <Phone size={18} />
                  </button>
                  <button type="button" disabled aria-label="Video call" className="rounded-lg p-2 opacity-40">
                    <Video size={18} />
                  </button>
                  <button type="button" disabled aria-label="More options" className="rounded-lg p-2 opacity-40">
                    <MoreVertical size={18} />
                  </button>
                </div>
              </header>

              <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 text-center">
                <div className="rounded-2xl bg-blue-50 p-5">
                  <MessageSquare size={34} className="text-blue-600" />
                </div>
                <h3 className="mt-5 text-lg font-semibold text-slate-800">
                  Your conversations, all in one place
                </h3>
                <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
                  Select a customer conversation to view message history and respond.
                  Connect your messaging channels to get started.
                </p>
              </div>

              <form
                onSubmit={(event) => event.preventDefault()}
                className="border-t border-slate-100 p-4"
              >
                <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <button type="button" disabled aria-label="Attach file" className="text-slate-300">
                    <Paperclip size={19} />
                  </button>
                  <input
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    disabled
                    placeholder="Select a conversation before sending a message..."
                    className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
                  />
                  <button
                    type="submit"
                    disabled
                    aria-label="Send message"
                    className="rounded-lg bg-blue-600 p-2 text-white opacity-40"
                  >
                    <Send size={17} />
                  </button>
                </div>
                <p className="mt-2 text-center text-[11px] text-slate-400">
                  Messaging will be enabled after channel and API integration.
                </p>
              </form>
            </section>
          </section>
        </div>
      </main>
    </div>
  );
}
