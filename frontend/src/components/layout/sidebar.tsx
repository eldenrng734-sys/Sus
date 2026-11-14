"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  LayoutDashboard,
  Users,
  CheckSquare,
  MessageSquare,
  Plug,
  Settings,
  LogOut,
} from "lucide-react";
import { logout } from "@/lib/api/auth";
import { cn } from "@/lib/utils";

const navigation = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Leads", href: "/leads", icon: Users },
  { label: "Tasks", href: "/tasks", icon: CheckSquare },
  { label: "Conversations", href: "/conversations", icon: MessageSquare },
  { label: "Integrations", href: "/integrations", icon: Plug },
  { label: "Settings", href: "/settings", icon: Settings },
];

async function handleLogout() {
  try {
    await logout();
  } finally {
    window.location.href = "/login";
  }
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex h-20 items-center gap-3 border-b border-slate-100 px-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 font-bold text-white shadow-sm">
          S
        </div>
        <div>
          <p className="text-lg font-bold tracking-wide text-slate-900">
            SYNTRIX
          </p>
          <p className="text-xs text-slate-500">AI Sales Assistant</p>
        </div>
      </div>

      <div className="px-4 pt-7">
        <p className="mb-3 px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Workspace
        </p>

        <nav className="space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                className={`flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition-colors ${
                  active
                    ? "bg-blue-50 text-blue-700"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                <Icon size={19} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto border-t border-slate-100 p-4">
        <div className="mb-4 flex items-center gap-3 rounded-lg bg-slate-50 p-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">
            U
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-800">
              Your workspace
            </p>
            <p className="text-xs text-slate-500">Sales team</p>
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium text-slate-600 transition hover:bg-red-50 hover:text-red-600"
        >
          <LogOut size={18} />
          Sign out
        </button>
      </div>
    </div>
  );
}

function MobileMenuButton({
  open,
  onClick,
}: {
  open: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={open ? "Close navigation menu" : "Open navigation menu"}
      aria-expanded={open}
      aria-controls="mobile-navigation"
      className="flex size-11 items-center justify-center rounded-xl border border-slate-200/90 bg-white/90 text-slate-700 shadow-sm backdrop-blur-sm transition-[background-color,box-shadow,transform] duration-200 ease-out hover:bg-white hover:text-slate-900 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/50 focus-visible:ring-offset-2 active:scale-95 motion-reduce:transition-none motion-reduce:active:scale-100"
    >
      <span
        aria-hidden="true"
        className="flex h-4 w-5 flex-col justify-between"
      >
        <span
          className={cn(
            "h-0.5 w-5 origin-center rounded-full bg-current transition-all duration-300 ease-out motion-reduce:transition-none",
            open && "translate-y-[7px] rotate-45"
          )}
        />
        <span
          className={cn(
            "h-0.5 w-5 origin-center rounded-full bg-current transition-all duration-300 ease-out motion-reduce:transition-none",
            open ? "opacity-0" : "opacity-100"
          )}
        />
        <span
          className={cn(
            "h-0.5 w-5 origin-center rounded-full bg-current transition-all duration-300 ease-out motion-reduce:transition-none",
            open && "-translate-y-[7px] -rotate-45"
          )}
        />
      </span>
    </button>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);

  const closeMobileNav = useCallback(() => setMobileOpen(false), []);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Close the drawer if the viewport grows to the desktop layout so the
  // scroll lock is always released.
  useEffect(() => {
    if (!mobileOpen) return;

    const desktopQuery = window.matchMedia("(min-width: 768px)");
    const handleDesktop = () => {
      if (desktopQuery.matches) setMobileOpen(false);
    };

    desktopQuery.addEventListener("change", handleDesktop);

    return () => {
      desktopQuery.removeEventListener("change", handleDesktop);
    };
  }, [mobileOpen]);

  // Prevent the page behind the drawer from scrolling while it is open.
  useEffect(() => {
    if (!mobileOpen) return;

    const previousHtmlOverflow = document.documentElement.style.overflow;
    const previousOverflow = document.body.style.overflow;
    const previousOverscroll = document.body.style.overscrollBehavior;

    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    document.body.style.overscrollBehavior = "none";

    return () => {
      document.documentElement.style.overflow = previousHtmlOverflow;
      document.body.style.overflow = previousOverflow;
      document.body.style.overscrollBehavior = previousOverscroll;
    };
  }, [mobileOpen]);

  // Move focus into the drawer, keep Tab inside it, close on Escape,
  // and restore focus to the menu button afterwards.
  useEffect(() => {
    if (!mobileOpen) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    drawerRef.current?.focus({ preventScroll: true });

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileOpen(false);
        return;
      }

      if (event.key !== "Tab") return;

      const drawer = drawerRef.current;
      if (!drawer) return;

      const focusable = Array.from(
        drawer.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      ).filter((element) => element.offsetParent !== null);

      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const focusIsInside = drawer.contains(active);

      if (event.shiftKey) {
        if (active === first || active === drawer || !focusIsInside) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || active === drawer || !focusIsInside) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);

      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus({ preventScroll: true });
      }
    };
  }, [mobileOpen]);

  return (
    <>
      <aside className="hidden min-h-screen w-64 shrink-0 border-r border-slate-200 bg-white md:block">
        <SidebarContent />
      </aside>

      <div className="fixed right-4 top-4 z-[60] md:hidden">
        <MobileMenuButton
          open={mobileOpen}
          onClick={() => setMobileOpen((current) => !current)}
        />
      </div>

      <div
        aria-hidden="true"
        onClick={closeMobileNav}
        className={cn(
          "fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-[1px] transition-opacity duration-300 ease-out md:hidden motion-reduce:transition-none",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0"
        )}
      />

      <aside
        id="mobile-navigation"
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation menu"
        aria-hidden={!mobileOpen}
        inert={!mobileOpen}
        tabIndex={-1}
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-72 max-w-[calc(100vw-4.5rem)] overflow-y-auto overscroll-contain bg-white shadow-2xl outline-none transition-transform duration-300 ease-out md:hidden motion-reduce:transition-none",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <SidebarContent onNavigate={closeMobileNav} />
      </aside>
    </>
  );
}
