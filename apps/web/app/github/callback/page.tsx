"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "../../../lib/api";

function GitHubCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"verifying" | "success" | "error">("verifying");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const installationIdStr = searchParams.get("installation_id");
    const setupAction = searchParams.get("setup_action");
    const errorParam = searchParams.get("error");
    const errorDescription = searchParams.get("error_description");

    if (errorParam) {
      setStatus("error");
      setErrorMessage(errorDescription || `GitHub returned error: ${errorParam}`);
      return;
    }

    if (!installationIdStr) {
      setStatus("error");
      setErrorMessage("No installation ID received from GitHub.");
      return;
    }

    const installationId = parseInt(installationIdStr, 10);
    if (isNaN(installationId) || installationId <= 0) {
      setStatus("error");
      setErrorMessage("Invalid installation ID received from GitHub.");
      return;
    }

    // Verify and link installation with CodeGuard backend
    api
      .verifyGitHubInstallation(installationId)
      .then(() => {
        setStatus("success");
        // Forward to repositories page with query params so repository discovery drawer opens automatically
        router.replace(`/repositories?installation_id=${installationId}&setup_action=${setupAction || "install"}`);
      })
      .catch((err) => {
        console.error("Installation verification error:", err);
        setStatus("error");
        setErrorMessage(
          err.message || "Failed to verify GitHub installation. Please try again."
        );
      });
  }, [searchParams, router]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="max-w-md w-full p-8 bg-surface-container border border-[#333842] rounded-xl shadow-2xl text-center space-y-4">
        {status === "verifying" && (
          <div className="space-y-4">
            <div className="w-12 h-12 rounded-full border-4 border-primary-fixed border-t-transparent animate-spin mx-auto" />
            <h2 className="font-headline-md text-headline-md text-primary font-bold">Connecting GitHub...</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              Verifying CodeGuard GitHub App installation and discovering accessible repositories.
            </p>
          </div>
        )}

        {status === "success" && (
          <div className="space-y-4">
            <div className="w-12 h-12 rounded-full bg-tertiary-container/20 border border-tertiary-fixed-dim text-tertiary-fixed-dim flex items-center justify-center mx-auto text-xl font-bold">
              ✓
            </div>
            <h2 className="font-headline-md text-headline-md text-primary font-bold">GitHub Connected!</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              Redirecting to repositories to select which projects to monitor...
            </p>
          </div>
        )}

        {status === "error" && (
          <div className="space-y-4">
            <div className="w-12 h-12 rounded-full bg-error-container/20 border border-error text-error flex items-center justify-center mx-auto text-xl font-bold">
              ✕
            </div>
            <h2 className="font-headline-md text-headline-md text-primary font-bold">Connection Failed</h2>
            <p className="font-body-sm text-body-sm text-error bg-error-container/10 p-3 rounded border border-error/30 font-mono">
              {errorMessage}
            </p>
            <div className="pt-2">
              <Link
                href="/repositories"
                className="inline-flex items-center px-4 py-2 rounded-lg font-headline-sm text-body-sm font-semibold bg-primary-container text-on-primary-container hover:brightness-105 transition shadow-sm"
              >
                Return to Repositories
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function GitHubCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-[60vh] flex items-center justify-center text-slate-500 font-mono text-sm">
          Loading callback...
        </div>
      }
    >
      <GitHubCallbackContent />
    </Suspense>
  );
}
