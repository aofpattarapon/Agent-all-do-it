"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiClient } from "@/lib/api-client";
import { PixelButton, PixelFrame, PixelToggle, SectionLabel } from "@/components/pixel-ui";

interface NotificationConfig {
  discord_enabled: boolean;
  discord_webhook_url: string;
  email_enabled: boolean;
  in_app_enabled: boolean;
  notify_on_approval: boolean;
  notify_on_run_failed: boolean;
  notify_on_run_complete: boolean;
  notify_on_budget_alert: boolean;
}

const DEFAULT_CONFIG: NotificationConfig = {
  discord_enabled: false,
  discord_webhook_url: "",
  email_enabled: false,
  in_app_enabled: true,
  notify_on_approval: true,
  notify_on_run_failed: true,
  notify_on_run_complete: false,
  notify_on_budget_alert: true,
};

export default function NotificationCenterPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<NotificationConfig>(DEFAULT_CONFIG);
  const [webhookVisible, setWebhookVisible] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);

  const configQuery = useQuery<NotificationConfig, ApiError>({
    queryKey: ["notification-config"],
    queryFn: () => apiClient.get("/notification-config"),
    retry: false,
  });

  useEffect(() => {
    if (configQuery.data) {
      setForm(configQuery.data);
    }
  }, [configQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (body: NotificationConfig) => apiClient.patch("/notification-config", body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["notification-config"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => apiClient.post("/notification-config/test", {}),
    onSuccess: () => setTestMessage("Test notification sent."),
    onError: (error) =>
      setTestMessage(error instanceof ApiError ? error.message : "Test failed."),
  });

  const stubMode = configQuery.error?.status === 501;

  function toggle<K extends keyof NotificationConfig>(key: K) {
    setForm((current) => ({ ...current, [key]: !current[key] }));
  }

  const webhookPreview =
    form.discord_webhook_url && !webhookVisible
      ? `${form.discord_webhook_url.slice(0, 8)}***`
      : form.discord_webhook_url;

  return (
    <>
      <PixelFrame tight>
        <div className="pix-eyebrow">Hub Management</div>
        <h2 style={{ margin: 0 }}>Notification Center</h2>
        <div className="pix-mono" style={{ fontSize: 13, marginTop: 4, color: "var(--pix-ink-soft)" }}>
          Configure where and when you receive alerts from the agent hub.
        </div>
      </PixelFrame>

      {stubMode && (
        <PixelFrame>
          <div className="pix-mono" style={{ color: "#e7b53c", fontSize: 13 }}>
            Notification backend endpoints are not implemented yet. This page is running in stub mode.
          </div>
        </PixelFrame>
      )}

      {configQuery.isLoading ? (
        <PixelFrame>
          <div className="pix-empty">Loading…</div>
        </PixelFrame>
      ) : (
        <>
          <PixelFrame>
            <SectionLabel>Discord Integration</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <PixelToggle on={form.discord_enabled} onChange={() => toggle("discord_enabled")} />
                <span className="pix-mono" style={{ fontSize: 15 }}>
                  Enable Discord notifications
                </span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)" }}>
                  Discord Webhook URL
                </label>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    type={webhookVisible ? "text" : "password"}
                    value={form.discord_webhook_url}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, discord_webhook_url: event.target.value }))
                    }
                    placeholder="https://discord.com/api/webhooks/..."
                    className="pix-mono"
                    style={{
                      flex: 1,
                      background: "var(--pix-parch2)",
                      border: "2px solid var(--pix-frame)",
                      padding: "5px 10px",
                      fontSize: 14,
                    }}
                  />
                  <PixelButton onClick={() => setWebhookVisible((value) => !value)}>
                    {webhookVisible ? "Hide" : "Show"}
                  </PixelButton>
                </div>
                {webhookPreview && !webhookVisible && (
                  <span className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>
                    {webhookPreview}
                  </span>
                )}
              </div>

              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <PixelButton
                  onClick={() => {
                    setTestMessage(null);
                    testMutation.mutate();
                  }}
                  disabled={testMutation.isPending || !form.discord_webhook_url}
                >
                  {testMutation.isPending ? "Sending…" : "Send Test"}
                </PixelButton>
                {testMessage && (
                  <span
                    className="pix-mono"
                    style={{
                      fontSize: 13,
                      color: testMutation.isError ? "#df5b53" : "#6fe08c",
                    }}
                  >
                    {testMessage}
                  </span>
                )}
              </div>
            </div>
          </PixelFrame>

          <PixelFrame>
            <SectionLabel>Notification Channels</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {([
                { key: "email_enabled", label: "Email notifications" },
                { key: "in_app_enabled", label: "In-app notifications" },
              ] as { key: keyof NotificationConfig; label: string }[]).map(({ key, label }) => (
                <div key={key} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <PixelToggle on={Boolean(form[key])} onChange={() => toggle(key)} />
                  <span className="pix-mono" style={{ fontSize: 15 }}>
                    {label}
                  </span>
                </div>
              ))}
            </div>
          </PixelFrame>

          <PixelFrame>
            <SectionLabel>Notification Events</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {([
                {
                  key: "notify_on_approval",
                  label: "Notify on trade/approval request",
                  description: "Alert when a run pauses waiting for human approval.",
                },
                {
                  key: "notify_on_run_failed",
                  label: "Notify on run failed",
                  description: "Alert on workflow failure.",
                },
                {
                  key: "notify_on_run_complete",
                  label: "Notify on run complete",
                  description: "Alert when a workflow finishes successfully.",
                },
                {
                  key: "notify_on_budget_alert",
                  label: "Notify on budget alert",
                  description: "Alert when daily spend exceeds the configured threshold.",
                },
              ] as { key: keyof NotificationConfig; label: string; description: string }[]).map(
                ({ key, label, description }) => (
                  <div key={key} style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                    <PixelToggle on={Boolean(form[key])} onChange={() => toggle(key)} />
                    <div>
                      <div className="pix-mono" style={{ fontSize: 15 }}>
                        {label}
                      </div>
                      <div className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>
                        {description}
                      </div>
                    </div>
                  </div>
                ),
              )}
            </div>
          </PixelFrame>

          <PixelFrame variant="screen">
            <SectionLabel>
              <span style={{ color: "#9bdbaa" }}>Escalation Policy</span>
            </SectionLabel>
            <div className="pix-mono" style={{ fontSize: 14, color: "#9bdbaa", lineHeight: 1.6 }}>
              <div>T+0 min — Initial alert sent via all configured channels.</div>
              <div>T+2 min — Reminder sent if no action has been taken.</div>
              <div>T+5 min — Run auto-rejected and manager notified.</div>
            </div>
          </PixelFrame>

          <PixelFrame tight>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <PixelButton
                variant="green"
                onClick={() => saveMutation.mutate(form)}
                disabled={saveMutation.isPending}
              >
                {saveMutation.isPending ? "Saving…" : "Save Preferences"}
              </PixelButton>
              {saveMutation.isError && (
                <span className="pix-mono" style={{ fontSize: 13, color: "#df5b53" }}>
                  {saveMutation.error instanceof ApiError
                    ? saveMutation.error.message
                    : "Failed to save preferences"}
                </span>
              )}
              {saveMutation.isSuccess && (
                <span className="pix-mono" style={{ fontSize: 13, color: "#6fe08c" }}>
                  Saved.
                </span>
              )}
            </div>
          </PixelFrame>
        </>
      )}
    </>
  );
}
