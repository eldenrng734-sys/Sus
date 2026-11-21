"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Bell,
  Check,
  CheckCheck,
  UserPlus,
  ExternalLink,
  Inbox,
} from "lucide-react";
import {
  useNotifications,
  useMarkNotificationRead,
  useMarkAllNotificationsRead,
} from "@/hooks/use-notifications";
import type { NotificationItem } from "@/lib/api/notifications";
import { cn } from "@/lib/utils";

export interface NotificationBellProps {
  /**
   * Preferred placement of the notification tray popover.
   * - "sidebar": Opens to the right of the sidebar on desktop (bottom-aligned),
   *   and centered above the profile card on mobile.
   * - "header": Opens below the bell, aligned to the right edge (standard header dropdown).
   * - "auto": Automatically detects if mounted inside a sidebar (<aside>) or header.
   */
  placement?: "sidebar" | "header" | "auto";
  className?: string;
}

export function NotificationBell({
  placement = "auto",
  className,
}: NotificationBellProps = {}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [resolvedPlacement, setResolvedPlacement] = useState<"sidebar" | "header">(
    placement === "auto" ? "sidebar" : placement
  );

  // Poll unread every 60 seconds
  const { data, isLoading } = useNotifications({ limit: 15 });
  const markReadMutation = useMarkNotificationRead();
  const markAllReadMutation = useMarkAllNotificationsRead();

  const unreadCount = data?.unread_count ?? 0;
  const notifications = data?.notifications ?? [];

  // Determine actual placement based on DOM context when "auto"
  useEffect(() => {
    if (placement !== "auto") {
      setResolvedPlacement(placement);
      return;
    }
    if (containerRef.current) {
      const isInsideAside = Boolean(containerRef.current.closest("aside, [data-slot='sidebar']"));
      const rect = containerRef.current.getBoundingClientRect();
      const isBottomHalf = rect.top > window.innerHeight / 2;
      setResolvedPlacement(isInsideAside || isBottomHalf ? "sidebar" : "header");
    }
  }, [placement, isOpen]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleMarkRead = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    e.preventDefault();
    markReadMutation.mutate(id);
  };

  const handleMarkAllRead = () => {
    markAllReadMutation.mutate();
  };

  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);

      if (diffMins < 1) return "Just now";
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      return date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      });
    } catch {
      return "";
    }
  };

  // Position classes based on resolved placement
  const trayPositionClasses =
    resolvedPlacement === "sidebar"
      ? "fixed inset-x-4 bottom-20 z-[70] max-w-sm mx-auto md:absolute md:inset-auto md:left-full md:bottom-0 md:ml-3 md:w-80 lg:w-96 md:max-w-none"
      : "absolute right-0 top-full mt-2 z-50 w-80 sm:w-96";

  return (
    <div className={cn("relative", className)} ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={cn(
          "relative flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border transition",
          "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900",
          "dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-white",
          isOpen &&
            "border-blue-500 bg-blue-50/60 text-blue-600 dark:border-blue-500 dark:bg-blue-950/40 dark:text-blue-400",
          "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
        )}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
        aria-expanded={isOpen}
        title="Notifications"
      >
        <Bell size={18} />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white shadow-sm ring-2 ring-white dark:ring-slate-900">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className={cn(
            trayPositionClasses,
            "flex max-h-[min(30rem,calc(100vh-6rem))] flex-col rounded-xl border border-slate-200 bg-white shadow-2xl ring-1 ring-black/5 animate-in fade-in zoom-in-95 [animation-duration:150ms]",
            "dark:border-slate-800 dark:bg-slate-900 dark:ring-white/10"
          )}
        >
          {/* Header */}
          <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-800">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                Notifications
              </h3>
              {unreadCount > 0 && (
                <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
                  {unreadCount} new
                </span>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                disabled={markAllReadMutation.isPending}
                className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800 disabled:opacity-50 dark:text-blue-400 dark:hover:text-blue-300"
              >
                <CheckCheck size={14} />
                Mark all read
              </button>
            )}
          </div>

          {/* List */}
          <div className="flex-1 divide-y divide-slate-100 overflow-y-auto overscroll-contain dark:divide-slate-800">
            {isLoading ? (
              <div className="py-8 text-center text-xs text-slate-400 dark:text-slate-500">
                Loading notifications...
              </div>
            ) : notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <div className="rounded-full bg-slate-100 p-3 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                  <Inbox size={22} />
                </div>
                <p className="mt-2 text-sm font-medium text-slate-800 dark:text-slate-200">
                  All caught up!
                </p>
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  You have no pending notifications right now.
                </p>
              </div>
            ) : (
              notifications.map((item: NotificationItem) => {
                const isUnread = !item.read_at;
                const linkHref =
                  item.entity_type === "lead"
                    ? `/leads/${item.entity_id}`
                    : null;

                const content = (
                  <div
                    className={cn(
                      "flex items-start gap-3 p-4 transition hover:bg-slate-50 dark:hover:bg-slate-800/60",
                      isUnread
                        ? "bg-blue-50/40 dark:bg-blue-950/20"
                        : "bg-transparent"
                    )}
                  >
                    <div
                      className={cn(
                        "mt-0.5 rounded-lg p-2 shrink-0",
                        isUnread
                          ? "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300"
                          : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                      )}
                    >
                      <UserPlus size={16} />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p
                          className={cn(
                            "text-sm leading-snug",
                            isUnread
                              ? "font-semibold text-slate-900 dark:text-slate-100"
                              : "font-medium text-slate-700 dark:text-slate-300"
                          )}
                        >
                          {item.title}
                        </p>
                        <span className="shrink-0 text-[11px] text-slate-400 dark:text-slate-500">
                          {formatTime(item.created_at)}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                        {item.body}
                      </p>

                      <div className="mt-2 flex items-center justify-between">
                        {linkHref ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:underline dark:text-blue-400">
                            View Lead <ExternalLink size={11} />
                          </span>
                        ) : (
                          <span />
                        )}

                        {isUnread && (
                          <button
                            type="button"
                            onClick={(e) => handleMarkRead(e, item.id)}
                            disabled={markReadMutation.isPending}
                            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                            title="Mark as read"
                          >
                            <Check size={12} />
                            Mark read
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );

                return linkHref ? (
                  <Link
                    key={item.id}
                    href={linkHref}
                    onClick={() => {
                      if (isUnread) markReadMutation.mutate(item.id);
                      setIsOpen(false);
                    }}
                    className="block text-left"
                  >
                    {content}
                  </Link>
                ) : (
                  <div key={item.id}>{content}</div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
