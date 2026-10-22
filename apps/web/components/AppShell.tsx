"use client";

import React, { useState } from "react";
import { Sidebar } from "./Sidebar";
import { TopHeader } from "./TopHeader";

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

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
