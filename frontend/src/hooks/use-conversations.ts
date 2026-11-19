import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getConversations,
  getConversation,
  getMessages,
  sendMessage,
} from "@/lib/api/conversations";

export function useConversations(params?: {
  channel?: string;
  status?: string;
  lead_id?: string;
}) {
  return useQuery({
    queryKey: ["conversations", params?.channel, params?.status, params?.lead_id],
    queryFn: () => getConversations(params),
  });
}

export function useConversation(conversationId?: string) {
  return useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => getConversation(conversationId!),
    enabled: Boolean(conversationId),
  });
}

export function useMessages(conversationId?: string) {
  return useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => getMessages(conversationId!),
    enabled: Boolean(conversationId),
    refetchInterval: 10_000, // Light polling every 10s for new inbound messages
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      conversation_id: string;
      text?: string;
      template?: {
        name: string;
        language: string;
        params: string[];
      };
    }) => sendMessage(payload),
    onSuccess: (newMessage, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["messages", variables.conversation_id],
      });
      void queryClient.invalidateQueries({
        queryKey: ["conversations"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["conversation", variables.conversation_id],
      });
    },
  });
}
