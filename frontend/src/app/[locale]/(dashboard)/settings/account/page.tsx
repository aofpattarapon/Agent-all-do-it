"use client";

import { useState } from "react";
import { AlertTriangle, Lock } from "lucide-react";
import { toast } from "sonner";

import { SettingsSection } from "@/components/settings/settings-section";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  Button,
  Input,
  Label,
} from "@/components/ui";
import { useAuth } from "@/hooks";
import { apiClient, ApiError } from "@/lib/api-client";

export default function AccountSettingsPage() {
  const { user, logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleChangePassword = async () => {
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    setSaving(true);
    try {
      await apiClient.post("/auth/password/change", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      toast.success("Password updated");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      // Backend may not have this endpoint yet — surface a helpful message.
      if (err instanceof ApiError && err.status === 404) {
        toast.error("Password change requires backend wiring (POST /auth/password/change).");
      } else {
        toast.error(err instanceof ApiError ? err.message : "Failed to update password");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!user) return;
    setDeleting(true);
    try {
      await apiClient.delete(`/users/${user.id}`);
      toast.success("Account deleted");
      logout();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        toast.error("Self-delete not enabled. Contact support.");
      } else {
        toast.error(err instanceof ApiError ? err.message : "Failed to delete account");
      }
    } finally {
      setDeleting(false);
    }
  };

  const pixInputStyle: React.CSSProperties = {
    background: "var(--pix-parch-2)",
    border: "2px solid var(--pix-wood-dark)",
    borderRadius: 0,
    fontFamily: '"VT323", monospace',
    fontSize: "18px",
    color: "var(--pix-ink)",
    height: "40px",
  };

  const pixLabelStyle: React.CSSProperties = {
    fontFamily: '"VT323", monospace',
    fontSize: "15px",
    letterSpacing: "0.1em",
    textTransform: "uppercase" as const,
    color: "var(--pix-ink)",
  };

  return (
    <div className="pix-root space-y-6">
      <SettingsSection
        title="Change password"
        description="Use a strong, unique password — 8+ characters, mixed case, numbers."
        action={
          <Button
            onClick={handleChangePassword}
            disabled={saving || !currentPassword || !newPassword}
            size="sm"
            style={{
              fontFamily: '"Pixelify Sans", sans-serif',
              background: "var(--pix-gold-dark)",
              color: "var(--pix-parch)",
              border: "2px solid var(--pix-wood-darkest)",
              borderRadius: 0,
              boxShadow: "0 3px 0 var(--pix-wood-darkest)",
            }}
          >
            {saving ? "Saving…" : "Update password"}
          </Button>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="current-pw" style={pixLabelStyle}>
              Current password
            </Label>
            <Input
              id="current-pw"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              style={pixInputStyle}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="new-pw" style={pixLabelStyle}>
                New password
              </Label>
              <Input
                id="new-pw"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                style={pixInputStyle}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="confirm-pw" style={pixLabelStyle}>
                Confirm new password
              </Label>
              <Input
                id="confirm-pw"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                style={pixInputStyle}
              />
            </div>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Sign out everywhere"
        description="Revoke every active session including this one. You'll be signed out immediately."
      >
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                background: "var(--pix-parch)",
                color: "var(--pix-ink)",
                border: "2px solid var(--pix-wood-dark)",
                borderRadius: 0,
              }}
            >
              <Lock className="mr-2 h-3.5 w-3.5" />
              Sign out everywhere
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Sign out from all devices?</AlertDialogTitle>
              <AlertDialogDescription>
                This revokes every active session and signs you out of this device too.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={async () => {
                  try {
                    await apiClient.delete("/sessions");
                    toast.success("Signed out from all devices");
                    logout();
                  } catch {
                    toast.error("Failed to sign out everywhere");
                  }
                }}
              >
                Sign out everywhere
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </SettingsSection>

      <SettingsSection
        title="Delete account"
        description="Permanently remove your account, conversations, and uploaded data. This can't be undone."
        danger
      >
        <div
          className="flex items-start gap-3 p-4"
          style={{
            background: "rgba(217,84,77,0.07)",
            border: "2px solid var(--pix-red)",
          }}
        >
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center"
            style={{
              background: "rgba(217,84,77,0.15)",
              color: "var(--pix-red)",
              border: "2px solid var(--pix-red)",
            }}
          >
            <AlertTriangle className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                fontSize: "14px",
                fontWeight: 700,
                color: "var(--pix-red)",
              }}
            >
              This is irreversible
            </p>
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "14px",
                color: "var(--pix-ink-soft)",
                marginTop: "2px",
              }}
            >
              All conversations, knowledge base contents, API keys, and personal data will be
              permanently deleted. Active subscriptions will be canceled.
            </p>
          </div>
        </div>
        <div className="mt-4">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              variant="destructive"
              size="sm"
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                background: "var(--pix-red)",
                color: "var(--pix-parch)",
                border: "2px solid var(--pix-wood-darkest)",
                borderRadius: 0,
                boxShadow: "0 3px 0 var(--pix-wood-darkest)",
              }}
            >
              Delete my account
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete your account?</AlertDialogTitle>
              <AlertDialogDescription>
                Your conversations, knowledge base contents, API keys, and all personal data will be
                permanently deleted. Active subscriptions will be canceled. This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                disabled={deleting}
                onClick={handleDeleteAccount}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleting ? "Deleting…" : "Yes, delete my account"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        </div>
      </SettingsSection>
    </div>
  );
}
