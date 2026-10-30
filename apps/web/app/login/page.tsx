"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "../../lib/api";

function getSafeReturnUrl(target: string | null): string {
  if (!target) return "/dashboard";
  // Must be an internal relative path: starts with '/', not '//', no backslashes, no scheme colon
  if (target.startsWith("/") && !target.startsWith("//") && !target.includes("\\") && !target.includes(":")) {
    return target;
  }
  return "/dashboard";
}

function mapAuthError(code: string | null): string | null {
  if (!code) return null;
  switch (code) {
    case "invalid_oauth_state":
      return "OAuth state verification failed or state expired. Please try signing in again.";
    case "missing_oauth_state":
      return "OAuth state was missing from Google response. Please try signing in again.";
    case "missing_authorization_code":
      return "Authorization code was not provided by Google. Please try signing in again.";
    case "missing_oauth_cookie":
      return "Security verification cookie was missing. Please ensure cookies are enabled in your browser and try again.";
    case "token_exchange_failed":
    case "no_access_token":
      return "Failed to complete token exchange with Google. Please try signing in again.";
    case "server_oauth_unconfigured":
      return "Google OAuth is not configured on the CodeGuard server. Please contact your administrator.";
    case "userinfo_fetch_failed":
      return "Could not retrieve user identity profile from Google. Please try again.";
    case "invalid_identity_payload":
      return "Received incomplete identity profile from Google. Please verify your Google account details.";
    case "account_inactive":
      return "Your user account is inactive. Please contact your organization administrator.";
    case "no_organization_membership":
      return "No active organization membership found. Access requires verified organization enrollment.";
    case "oauth_network_error":
      return "Network communication error during Google authentication. Please retry.";
    case "access_denied":
      return "Sign-in request was cancelled or access was denied by Google.";
    default:
      return `Authentication error: ${code.replace(/_/g, " ")}`;
  }
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [loading, setLoading] = useState(false);
  const [checkingExistingSession, setCheckingExistingSession] = useState(true);

  const errorParam = searchParams.get("auth_error") || searchParams.get("error");
  const returnToParam = searchParams.get("return_to") || searchParams.get("redirect_url");

  const safeReturn = getSafeReturnUrl(returnToParam);
  const errorMessage = mapAuthError(errorParam);

  useEffect(() => {
    // If there is an authentication error in URL parameters, display it directly
    if (errorParam) {
      setCheckingExistingSession(false);
      return;
    }

    // Check for an existing authenticated session before presenting the sign-in button
    api
      .getAuthMe()
      .then((res) => {
        // Auto-redirect if an authentic session exists (exclude synthetic unauthenticated dev bypass)
        if (res?.authenticated && !res?.user?.is_dev) {
          router.replace(safeReturn);
        } else {
          setCheckingExistingSession(false);
        }
      })
      .catch(() => {
        setCheckingExistingSession(false);
      });
  }, [safeReturn, router, errorParam]);

  const handleGoogleLogin = () => {
    setLoading(true);
    const loginUrl = api.getGoogleLoginUrl(safeReturn);
    window.location.href = loginUrl;
  };

  return (
    <div className="w-full max-w-md bg-surface-container border border-[#262930] rounded-xl p-8 shadow-2xl relative z-10">
      {/* ── Brand Header ── */}
      <div className="flex flex-col items-center text-center">
        <div className="w-12 h-12 rounded-xl bg-primary-container text-on-primary-container flex items-center justify-center font-label-mono font-bold text-lg shadow-sm mb-3 border border-primary/20">
          CG
        </div>
        <div className="font-label-mono text-xs uppercase tracking-widest text-primary font-semibold mb-2">
          CodeGuard
        </div>
        <h1 className="font-headline-sm text-2xl font-bold text-on-surface tracking-tight">
          Welcome to CodeGuard
        </h1>
        <p className="font-body-md text-sm text-on-surface-variant mt-2 text-center">
          Sign in to review, analyze, and secure your code.
        </p>
      </div>

      {/* ── Error Banner ── */}
      {errorMessage && (
        <div
          role="alert"
          className="mt-6 p-4 rounded-lg border border-red-500/30 bg-red-500/10 text-red-300 text-xs flex items-start gap-3"
        >
          <span className="material-symbols-outlined text-red-400 text-lg shrink-0 mt-0.5">
            error
          </span>
          <div className="flex-1 font-body-md leading-relaxed">
            <span className="font-semibold block text-red-200 mb-0.5">Authentication Notice</span>
            {errorMessage}
          </div>
        </div>
      )}

      {/* ── Action Section ── */}
      <div className="mt-8 space-y-4">
        <p className="text-xs text-on-surface-variant text-center font-body-md leading-relaxed">
          Sign in with your enterprise Google account to access code intelligence, policy enforcement, and automated pull request reviews.
        </p>

        <button
          type="button"
          onClick={handleGoogleLogin}
          disabled={loading || checkingExistingSession}
          className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-lg bg-surface-container-highest hover:bg-surface-container-high border border-[#262930] hover:border-[#383c44] text-on-surface font-medium text-sm transition-all duration-150 shadow-sm hover:shadow active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          {loading || checkingExistingSession ? (
            <div className="flex items-center gap-2.5">
              <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <span className="text-xs font-label-mono text-outline">
                {checkingExistingSession ? "Verifying session..." : "Redirecting to Google..."}
              </span>
            </div>
          ) : (
            <>
              {/* Google 4-Color Official SVG */}
              <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                />
              </svg>
              <span>Continue with Google</span>
            </>
          )}
        </button>
      </div>

      {/* ── Security Trust Footer ── */}
      <div className="mt-8 pt-6 border-t border-[#262930] flex flex-col items-center text-center gap-2">
        <div className="flex items-center gap-1.5 text-[11px] text-outline font-label-mono">
          <span className="material-symbols-outlined text-[14px]">shield</span>
          <span>Zero-Trust Architecture & Deterministic Policies</span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-outline font-label-mono">
          <span>Enterprise SSO</span>
          <span>•</span>
          <span>HttpOnly Sessions</span>
          <span>•</span>
          <span>Tenant Isolated</span>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center px-4 py-12 relative overflow-hidden">
      {/* Subtle background glow consistent with CodeGuard dashboard styling */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-primary/5 rounded-full blur-3xl pointer-events-none" />

      <Suspense
        fallback={
          <div className="w-full max-w-md bg-surface-container border border-[#262930] rounded-xl p-8 shadow-2xl flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        }
      >
        <LoginForm />
      </Suspense>
    </div>
  );
}
