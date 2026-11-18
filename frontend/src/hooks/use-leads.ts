import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getLeads,
  getLead,
  updateLead,
  getLeadTimeline,
  addLeadNote,
  reviewAssessment,
  importLeadsCsv,
  type LeadStatus,
  type LostReason,
  type LeadPriority,
} from "@/lib/api/leads";

export function useLeads(params: URLSearchParams) {
  const queryKey = ["leads", params.toString()];
  return useQuery({
    queryKey,
    queryFn: () => getLeads(params),
  });
}

export function useLead(id: string) {
  return useQuery({
    queryKey: ["lead", id],
    queryFn: () => getLead(id),
    enabled: Boolean(id),
  });
}

export function useLeadTimeline(leadId: string) {
  return useQuery({
    queryKey: ["lead-timeline", leadId],
    queryFn: () => getLeadTimeline(leadId),
    enabled: Boolean(leadId),
  });
}

export function useUpdateLead(leadId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      version: number;
      status?: LeadStatus;
      lost_reason?: LostReason | null;
      reopen_reason?: string | null;
      name?: string;
      priority?: LeadPriority;
      email?: string | null;
      phone?: string | null;
      company_name?: string | null;
    }) => updateLead(leadId, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(["lead", leadId], updated);
      void queryClient.invalidateQueries({ queryKey: ["leads"] });
      void queryClient.invalidateQueries({ queryKey: ["lead-timeline", leadId] });
    },
  });
}

export function useAddLeadNote(leadId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (text: string) => addLeadNote(leadId, text),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lead-timeline", leadId] });
    },
  });
}

export function useReviewAssessment(leadId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      assessmentId,
      reviewStatus,
      reviewNote,
    }: {
      assessmentId: string;
      reviewStatus: "approved" | "rejected";
      reviewNote?: string | null;
    }) =>
      reviewAssessment(assessmentId, {
        review_status: reviewStatus,
        review_note: reviewNote,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lead", leadId] });
      void queryClient.invalidateQueries({ queryKey: ["lead-timeline", leadId] });
    },
  });
}

export function useImportCsv() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file, dryRun }: { file: File; dryRun?: boolean }) =>
      importLeadsCsv(file, dryRun),
    onSuccess: (result) => {
      if (!result.dry_run) {
        void queryClient.invalidateQueries({ queryKey: ["leads"] });
      }
    },
  });
}
