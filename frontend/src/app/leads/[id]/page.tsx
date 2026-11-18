"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  Mail,
  Phone,
  Building,
  User,
  Sparkles,
  Smile,
  Meh,
  Frown,
  Check,
  X,
  MessageSquare,
  AlertCircle,
  FileText,
  Send,
  HelpCircle,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { useAuth } from "@/providers/auth-provider";
import {
  useLead,
  useLeadTimeline,
  useUpdateLead,
  useAddLeadNote,
  useReviewAssessment,
} from "@/hooks/use-leads";
import {
  LOST_REASONS,
  type LeadStatus,
  type LostReason,
  type TimelineEvent,
} from "@/lib/api/leads";
import { parseApiError } from "@/lib/api-error";
import { ErrorBanner } from "@/components/shared/error-banner";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { formatTenantDateTime } from "@/hooks/use-tasks";

const statuses: LeadStatus[] = [
  "new",
  "contacted",
  "qualified",
  "proposal",
  "won",
  "lost",
];

const statusStyles: Record<string, string> = {
  new: "bg-blue-50 text-blue-700 border-blue-200",
  contacted: "bg-cyan-50 text-cyan-700 border-cyan-200",
  qualified: "bg-emerald-50 text-emerald-700 border-emerald-200",
  proposal: "bg-violet-50 text-violet-700 border-violet-200",
  won: "bg-green-50 text-green-700 border-green-200",
  lost: "bg-red-50 text-red-700 border-red-200",
};

export default function LeadDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const { role, timezone } = useAuth();
  const isManagerOrAdmin = role === "manager" || role === "admin";

  const {
    data: lead,
    isLoading: isLoadingLead,
    isError: isLeadError,
    error: leadError,
    refetch: refetchLead,
  } = useLead(id);

  const {
    data: timeline = [],
    isLoading: isLoadingTimeline,
    refetch: refetchTimeline,
  } = useLeadTimeline(id);

  const updateLeadMutation = useUpdateLead(id);
  const addNoteMutation = useAddLeadNote(id);
  const reviewAssessmentMutation = useReviewAssessment(id);

  const [noteText, setNoteText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<{
    title: string;
    message: string;
  } | null>(null);

  // Lost reason modal state
  const [showLostModal, setShowLostModal] = useState(false);
  const [selectedLostReason, setSelectedLostReason] =
    useState<LostReason>("price");

  // Reopen prompt state (when moving from lost to contacted)
  const [showReopenModal, setShowReopenModal] = useState(false);
  const [reopenReason, setReopenReason] = useState("");

  // Assessment review note modal state
  const [reviewNoteModal, setReviewNoteModal] = useState<{
    open: boolean;
    decision: "approved" | "rejected";
    note: string;
  }>({ open: false, decision: "approved", note: "" });

  const handleStatusSelect = async (newStatus: LeadStatus) => {
    if (!lead || newStatus === lead.status) return;

    if (newStatus === "lost") {
      setShowLostModal(true);
      return;
    }

    if (lead.status === "lost" && newStatus === "contacted") {
      setShowReopenModal(true);
      return;
    }

    try {
      setErrorBanner(null);
      await updateLeadMutation.mutateAsync({
        version: lead.version,
        status: newStatus,
      });
      setNotice(`Lead status changed to ${newStatus}.`);
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleConfirmLost = async () => {
    if (!lead) return;
    try {
      setErrorBanner(null);
      await updateLeadMutation.mutateAsync({
        version: lead.version,
        status: "lost",
        lost_reason: selectedLostReason,
      });
      setShowLostModal(false);
      setNotice(`Lead marked as lost (${selectedLostReason}).`);
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleConfirmReopen = async () => {
    if (!lead) return;
    try {
      setErrorBanner(null);
      await updateLeadMutation.mutateAsync({
        version: lead.version,
        status: "contacted",
        reopen_reason: reopenReason.trim() || undefined,
      });
      setShowReopenModal(false);
      setReopenReason("");
      setNotice("Lead reopened to contacted.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleAssessmentDecision = async (
    decision: "approved" | "rejected",
    note?: string | null
  ) => {
    if (!lead?.latest_assessment) return;
    try {
      setErrorBanner(null);
      await reviewAssessmentMutation.mutateAsync({
        assessmentId: lead.latest_assessment.id,
        reviewStatus: decision,
        reviewNote: note || null,
      });
      setReviewNoteModal({ open: false, decision: "approved", note: "" });
      setNotice(
        decision === "approved"
          ? "AI assessment approved."
          : "AI assessment rejected."
      );
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  const handleAddNote = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = noteText.trim();
    if (!text) return;

    try {
      setErrorBanner(null);
      await addNoteMutation.mutateAsync(text);
      setNoteText("");
      setNotice("Note added to lead timeline.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      const parsed = parseApiError(err);
      setErrorBanner({ title: parsed.title, message: parsed.message });
    }
  };

  if (isLoadingLead) {
    return (
      <div className="flex min-h-screen bg-slate-50">
        <Sidebar />
        <main className="flex flex-1 items-center justify-center p-8">
          <LoadingSpinner size="lg" message="Loading lead details..." />
        </main>
      </div>
    );
  }

  if (isLeadError || !lead) {
    return (
      <div className="flex min-h-screen bg-slate-50">
        <Sidebar />
        <main className="flex-1 p-8">
          <Link
            href="/leads"
            className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
          >
            <ArrowLeft size={16} /> Back to leads
          </Link>
          <div className="mt-6 max-w-xl">
            <ErrorBanner
              error={leadError}
              title="Lead Not Found"
              message="The requested lead could not be loaded."
              onRetry={() => void refetchLead()}
            />
          </div>
        </main>
      </div>
    );
  }

  const assessment = lead.latest_assessment;

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <main className="min-w-0 flex-1">
        {/* Top Header */}
        <header className="flex min-h-20 items-center justify-between border-b border-slate-200 bg-white px-6 sm:px-8">
          <div>
            <Link
              href="/leads"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-blue-600"
            >
              <ArrowLeft size={14} /> Back to Leads
            </Link>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              {lead.name}
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <label
              htmlFor="lead-status"
              className="text-xs font-semibold uppercase tracking-wider text-slate-500"
            >
              Status:
            </label>
            <select
              id="lead-status"
              value={lead.status}
              disabled={updateLeadMutation.isPending}
              onChange={(e) => void handleStatusSelect(e.target.value as LeadStatus)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-bold uppercase transition focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                statusStyles[lead.status] || "bg-slate-100 text-slate-700"
              }`}
            >
              {statuses.map((st) => (
                <option key={st} value={st}>
                  {st.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
        </header>

        <div className="mx-auto max-w-7xl space-y-6 p-6 sm:p-8">
          {/* Notices & Banners */}
          {errorBanner && (
            <ErrorBanner
              title={errorBanner.title}
              message={errorBanner.message}
              onDismiss={() => setErrorBanner(null)}
              onRetry={() => {
                void refetchLead();
                void refetchTimeline();
              }}
            />
          )}

          {notice && (
            <div className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
              <span>{notice}</span>
              <button
                onClick={() => setNotice(null)}
                className="text-green-600 hover:text-green-800"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {/* Lost Status Notice */}
          {lead.status === "lost" && (
            <div className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-900">
              <div>
                <p className="font-semibold text-red-800">
                  Lead Closed — Status: Lost
                </p>
                <p className="mt-0.5 text-red-700">
                  Lost reason:{" "}
                  <span className="font-bold capitalize">
                    {lead.lost_reason
                      ? lead.lost_reason.replace("_", " ")
                      : "Unspecified"}
                  </span>
                </p>
              </div>
              <button
                onClick={() => handleStatusSelect("contacted")}
                className="rounded-lg bg-red-100 px-3 py-1.5 font-semibold text-red-800 hover:bg-red-200"
              >
                Reopen Lead
              </button>
            </div>
          )}

          {/* Grid Layout: Lead Info + AI Card */}
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Lead Information Card (2 cols) */}
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
              <h2 className="text-base font-bold text-slate-900">
                Lead Details
              </h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div className="flex items-start gap-3">
                  <Mail size={16} className="mt-1 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-400">Email Address</p>
                    <p className="text-sm font-medium text-slate-800">
                      {lead.email || "—"}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Phone size={16} className="mt-1 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-400">Phone</p>
                    <p className="text-sm font-medium text-slate-800">
                      {lead.phone || "—"}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Building size={16} className="mt-1 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-400">Company</p>
                    <p className="text-sm font-medium text-slate-800">
                      {lead.company_name || "—"}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <User size={16} className="mt-1 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-400">Assigned Owner</p>
                    <p className="text-sm font-medium text-slate-800">
                      {lead.owner?.full_name ||
                        lead.owner?.email ||
                        "Unassigned"}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Calendar size={16} className="mt-1 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-400">Lead Source</p>
                    <p className="text-sm font-medium capitalize text-slate-800">
                      {lead.source.replace("_", " ")}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Clock size={16} className="mt-1 text-slate-400" />
                  <div>
                    <p className="text-xs text-slate-400">Created At</p>
                    <p className="text-sm font-medium text-slate-800">
                      {formatTenantDateTime(lead.created_at || "", timezone)}
                    </p>
                  </div>
                </div>
              </div>

              {/* Next Task Banner */}
              {lead.next_task && (
                <div className="mt-6 rounded-xl border border-blue-100 bg-blue-50/60 p-4">
                  <p className="text-xs font-bold uppercase tracking-wider text-blue-700">
                    Next Due Task
                  </p>
                  <p className="mt-1 font-semibold text-slate-900">
                    {lead.next_task.title}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Type: {lead.next_task.type} · Due:{" "}
                    {formatTenantDateTime(lead.next_task.due_at, timezone)}
                  </p>
                </div>
              )}
            </section>

            {/* AI Intelligence Card (1 col) */}
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div className="flex items-center gap-2">
                  <Sparkles size={18} className="text-blue-600" />
                  <h2 className="text-base font-bold text-slate-900">
                    AI Assessment
                  </h2>
                </div>
                {assessment && (
                  <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
                    Score: {assessment.lead_score ?? lead.lead_score ?? "—"}
                  </span>
                )}
              </div>

              {assessment ? (
                <div className="mt-4 space-y-4 text-sm">
                  {/* Sentiment Badge */}
                  <div>
                    <p className="text-xs text-slate-400">Sentiment</p>
                    <div className="mt-1 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold capitalize">
                      {assessment.sentiment === "positive" ? (
                        <>
                          <Smile size={14} className="text-green-600" />
                          <span className="text-green-700">Positive</span>
                        </>
                      ) : assessment.sentiment === "negative" ? (
                        <>
                          <Frown size={14} className="text-red-600" />
                          <span className="text-red-700">Negative</span>
                        </>
                      ) : (
                        <>
                          <Meh size={14} className="text-slate-500" />
                          <span className="text-slate-700">
                            {assessment.sentiment || "Neutral"}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Intent & Priority */}
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <p className="text-xs text-slate-400">Intent</p>
                      <p className="mt-0.5 font-semibold capitalize text-slate-800">
                        {assessment.intent?.replace("_", " ") || "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-400">Priority</p>
                      <p className="mt-0.5 font-semibold capitalize text-slate-800">
                        {assessment.priority || "—"}
                      </p>
                    </div>
                  </div>

                  {/* Recommended Action */}
                  {assessment.recommended_action && (
                    <div>
                      <p className="text-xs text-slate-400">
                        Recommended Action
                      </p>
                      <p className="mt-0.5 font-semibold capitalize text-blue-700">
                        {assessment.recommended_action.replace("_", " ")}
                      </p>
                    </div>
                  )}

                  {/* Confidence */}
                  <div>
                    <p className="text-xs text-slate-400">Confidence</p>
                    <p className="mt-0.5 font-semibold text-slate-800">
                      {assessment.confidence != null
                        ? `${Math.round(assessment.confidence * 100)}%`
                        : "—"}
                    </p>
                  </div>

                  {/* AI Summary */}
                  {assessment.summary && (
                    <div>
                      <p className="text-xs text-slate-400">Summary</p>
                      <p className="mt-1 text-xs leading-relaxed text-slate-600">
                        {assessment.summary}
                      </p>
                    </div>
                  )}

                  {/* Review-state UX */}
                  <div className="border-t border-slate-100 pt-3">
                    {assessment.needs_human_review ||
                    assessment.review_status === "pending" ? (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs">
                        <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                          <AlertCircle size={14} className="text-amber-600" />
                          Human Review Required
                        </div>
                        <p className="mt-1 text-amber-800">
                          AI flagged this assessment for review.
                        </p>

                        {isManagerOrAdmin ? (
                          <div className="mt-3 flex gap-2">
                            <button
                              onClick={() =>
                                setReviewNoteModal({
                                  open: true,
                                  decision: "approved",
                                  note: "",
                                })
                              }
                              disabled={reviewAssessmentMutation.isPending}
                              className="inline-flex items-center gap-1 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700"
                            >
                              <Check size={12} />
                              Approve
                            </button>
                            <button
                              onClick={() =>
                                setReviewNoteModal({
                                  open: true,
                                  decision: "rejected",
                                  note: "",
                                })
                              }
                              disabled={reviewAssessmentMutation.isPending}
                              className="inline-flex items-center gap-1 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50"
                            >
                              <X size={12} />
                              Reject
                            </button>
                          </div>
                        ) : (
                          <p className="mt-2 text-xs italic text-amber-700">
                            Awaiting manager or admin approval.
                          </p>
                        )}
                      </div>
                    ) : assessment.review_status === "approved" ? (
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-green-700">
                        <CheckCircle2 size={15} />
                        Assessment Approved
                      </div>
                    ) : assessment.review_status === "rejected" ? (
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-red-600">
                        <X size={15} />
                        Assessment Rejected
                      </div>
                    ) : (
                      <div className="text-xs text-slate-400">
                        Automated Assessment (No Review Required)
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="mt-8 text-center text-xs text-slate-400">
                  <HelpCircle size={28} className="mx-auto text-slate-300" />
                  <p className="mt-2">No AI assessment generated yet.</p>
                </div>
              )}
            </section>
          </div>

          {/* Activity Timeline & Notes Section */}
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-bold text-slate-900">
              Activity Timeline & Notes
            </h2>

            {/* Note Submission Form */}
            <form onSubmit={handleAddNote} className="mt-4 space-y-3">
              <textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                maxLength={2000}
                rows={2}
                placeholder="Write an internal note for this lead..."
                className="w-full rounded-xl border border-slate-200 p-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={addNoteMutation.isPending || !noteText.trim()}
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  <Send size={13} />
                  {addNoteMutation.isPending ? "Adding note..." : "Add Note"}
                </button>
              </div>
            </form>

            {/* Timeline Stream */}
            <div className="mt-6 border-t border-slate-100 pt-6">
              {isLoadingTimeline ? (
                <div className="py-8 text-center text-xs text-slate-400">
                  <LoadingSpinner size="sm" message="Loading timeline..." />
                </div>
              ) : timeline.length === 0 ? (
                <p className="py-6 text-center text-xs text-slate-400">
                  No activity events recorded yet.
                </p>
              ) : (
                <ol className="relative space-y-4 border-l border-slate-200 ml-3">
                  {timeline.map((event: TimelineEvent, idx: number) => {
                    const isMessage = event.kind === "message";
                    const isNote = event.type === "note_added";

                    return (
                      <li key={idx} className="ml-6">
                        <span
                          className={`absolute -left-3 flex h-6 w-6 items-center justify-center rounded-full border border-white text-xs ${
                            isNote
                              ? "bg-amber-100 text-amber-700"
                              : isMessage
                              ? "bg-blue-100 text-blue-700"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {isNote ? (
                            <FileText size={12} />
                          ) : isMessage ? (
                            <MessageSquare size={12} />
                          ) : (
                            <CheckCircle2 size={12} />
                          )}
                        </span>

                        <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-3">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold capitalize text-slate-800">
                              {event.type.replace("_", " ")}
                            </span>
                            <time className="text-xs text-slate-400">
                              {formatTenantDateTime(event.at, timezone)}
                            </time>
                          </div>

                          {event.summary && (
                            <p className="mt-1 text-xs text-slate-700 whitespace-pre-wrap">
                              {event.summary}
                            </p>
                          )}

                          {event.details &&
                            typeof event.details.note === "string" && (
                              <p className="mt-1 text-xs italic text-slate-600">
                                &ldquo;{event.details.note}&rdquo;
                              </p>
                            )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>
          </section>
        </div>
      </main>

      {/* Lost Reason Modal */}
      {showLostModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-base font-bold text-slate-900">
              Select Lost Reason
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Please specify why this lead was lost for reporting accuracy.
            </p>

            <div className="mt-4 space-y-2">
              {LOST_REASONS.map((reason) => (
                <label
                  key={reason.value}
                  className={`flex cursor-pointer items-center justify-between rounded-xl border p-3 text-xs font-medium transition ${
                    selectedLostReason === reason.value
                      ? "border-red-500 bg-red-50/60 text-red-900"
                      : "border-slate-200 text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <span>{reason.label}</span>
                  <input
                    type="radio"
                    name="lost_reason"
                    checked={selectedLostReason === reason.value}
                    onChange={() => setSelectedLostReason(reason.value)}
                    className="text-red-600"
                  />
                </label>
              ))}
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowLostModal(false)}
                className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={updateLeadMutation.isPending}
                onClick={() => void handleConfirmLost()}
                className="rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {updateLeadMutation.isPending
                  ? "Marking Lost..."
                  : "Confirm Lost"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reopen Modal */}
      {showReopenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-base font-bold text-slate-900">Reopen Lead</h3>
            <p className="mt-1 text-xs text-slate-500">
              Optionally provide a reason for reopening this lead.
            </p>

            <input
              type="text"
              value={reopenReason}
              onChange={(e) => setReopenReason(e.target.value)}
              placeholder="e.g. Customer re-engaged via WhatsApp"
              className="mt-4 w-full rounded-lg border border-slate-200 p-2.5 text-xs outline-none focus:border-blue-500"
            />

            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowReopenModal(false)}
                className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={updateLeadMutation.isPending}
                onClick={() => void handleConfirmReopen()}
                className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
              >
                Reopen
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Assessment Review Note Modal */}
      {reviewNoteModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-base font-bold text-slate-900">
              {reviewNoteModal.decision === "approved"
                ? "Approve AI Assessment"
                : "Reject AI Assessment"}
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Optionally attach a note to this review decision.
            </p>

            <textarea
              value={reviewNoteModal.note}
              onChange={(e) =>
                setReviewNoteModal((curr) => ({
                  ...curr,
                  note: e.target.value,
                }))
              }
              rows={3}
              placeholder="Internal review note..."
              className="mt-4 w-full rounded-lg border border-slate-200 p-2.5 text-xs outline-none focus:border-blue-500"
            />

            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() =>
                  setReviewNoteModal({
                    open: false,
                    decision: "approved",
                    note: "",
                  })
                }
                className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={reviewAssessmentMutation.isPending}
                onClick={() =>
                  void handleAssessmentDecision(
                    reviewNoteModal.decision,
                    reviewNoteModal.note
                  )
                }
                className={`rounded-lg px-4 py-2 text-xs font-semibold text-white disabled:opacity-50 ${
                  reviewNoteModal.decision === "approved"
                    ? "bg-green-600 hover:bg-green-700"
                    : "bg-red-600 hover:bg-red-700"
                }`}
              >
                Confirm{" "}
                {reviewNoteModal.decision === "approved"
                  ? "Approval"
                  : "Rejection"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
