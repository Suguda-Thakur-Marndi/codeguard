"use client";

import React, { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { TopHeader } from "./TopHeader";
import { api, authStorage } from "../lib/api";

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  const isLoginPage = pathname === "/login";

  useEffect(() => {
    if (isLoginPage) return;

    // In browser, consume token from URL if returned from OAuth redirect
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const token = urlParams.get("token");
      if (token) {
        authStorage.setToken(token);
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }

    let isMounted = true;
    api
      .getAuthMe()
      .catch((err) => {
        if (!isMounted) return;
        // If unauthenticated (401), redirect to /login preserving return path
        if (err?.status === 401 || (err?.message && err.message.includes("401"))) {
          const returnTo = pathname && pathname !== "/" ? pathname : "/dashboard";
          router.replace(`/login?return_to=${encodeURIComponent(returnTo)}`);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [pathname, isLoginPage, router]);

  if (isLoginPage) {
    return (
      <div className="min-h-screen bg-surface font-body-md text-body-md text-on-surface antialiased">
        {children}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface font-body-md text-body-md text-on-surface antialiased flex flex-col">
      <Sidebar
        isOpen={mobileSidebarOpen}
        onClose={() => setMobileSidebarOpen(false)}
      />
      <TopHeader onToggleMobileSidebar={() => setMobileSidebarOpen(!mobileSidebarOpen)} />
      {/* md:pl-60 matches the sidebar w-60 */}
      <main className="flex-1 w-full pt-14 md:pl-60 min-h-screen bg-surface transition-all duration-200">
        <div className="w-full px-4 sm:px-5 lg:px-6 py-4 max-w-[1600px]">
          {children}
        </div>
      </main>
    </div>
  );
};
