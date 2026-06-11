"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { ApiError, apiClient } from "@/lib/api-client";
import { useConsoleData } from "@/components/console/use-console-data";
import { PixelButton, PixelFrame, PixelToggle, SectionLabel } from "@/components/pixel-ui";

type TriggerKind = "cron" | "webhook" | "event" | "manual";

interface Trigger {
  id: string;
  name: string;
  kind: TriggerKind;
  workflow_id: string | null;
  is_enabled: boolean;
  priority: number;
  cron_expression: string | null;
  webhook_path: string | null;
  filter_json: Record<string, unknown> | null;
}

interface TriggersResponse {
  items: Trigger[];
  total: number;
}

interface Workflow {
  id: string;
  name: string;
  key: string;
}

interface WorkflowsResponse {
  items: Workflow[];
}

interface TriggerForm {
  name: string;
  kind: TriggerKind;
  workflow_id: string;
  priority: number;
  cron_expression: string;
  webhook_path: string;
  filter_json: string;
}

const KIND_COLOR: Record<TriggerKind, string> = {
  cron: "#60a5fa",
  webhook: "#6fe08c",
  event: "#f97316",
  manual: "#9ca3af",
};

const EMPTY_FORM: TriggerForm = {
  name: "",
  kind: "manual",
  workflow_id: "",
  priority: 5,
  cron_expression: "",
  webhook_path: "",
  filter_json: "{}",
};

function KindBadge({ kind }: { kind: TriggerKind }) {
  return (
    <span
      className="pix-mono"
      style={{
        fontSize: 12,
        padding: "1px 7px",
        border: `2px solid ${KIND_COLOR[kind]}`,
        color: KIND_COLOR[kind],
        borderRadius: 2,
      }}
    >
      {kind}
    </span>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)" }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function triggerToForm(trigger: Trigger): TriggerForm {
  return {
    name: trigger.name,
    kind: trigger.kind,
    workflow_id: trigger.workflow_id ?? "",
    priority: trigger.priority,
    cron_expression: trigger.cron_expression ?? "",
    webhook_path: trigger.webhook_path ?? "",
    filter_json: trigger.filter_json ? JSON.stringify(trigger.filter_json, null, 2) : "{}",
  };
}

function TriggerDialog({
  projectId,
  workflows,
  initialTrigger,
  onClose,
}: {
  projectId: string;
  workflows: Workflow[];
  initialTrigger?: Trigger | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<TriggerForm>(
    initialTrigger
      ? triggerToForm(initialTrigger)
      : { ...EMPTY_FORM, workflow_id: workflows[0]?.id ?? "" },
  );
  const [generatedSecret, setGeneratedSecret] = useState<string | null>(null);

  const setField = <K extends keyof TriggerForm>(key: K, value: TriggerForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const payload = useMemo(() => {
    const body: Record<string, unknown> = {
      name: form.name,
      kind: form.kind,
      workflow_id: form.workflow_id || null,
      priority: form.priority,
    };
    if (form.kind === "cron") body.cron_expression = form.cron_expression;
    if (form.kind === "webhook") body.webhook_path = form.webhook_path;
    if (form.kind === "event") {
      try {
        body.filter_json = JSON.parse(form.filter_json);
      } catch {
        body.filter_json = {};
      }
    }
    return body;
  }, [form]);

  function generateSecret() {
    const bytes = new Uint8Array(24);
    crypto.getRandomValues(bytes);
    setGeneratedSecret(
      Array.from(bytes)
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join(""),
    );
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      initialTrigger
        ? apiClient.patch(`/projects/${projectId}/triggers/${initialTrigger.id}`, payload)
        : apiClient.post(`/projects/${projectId}/triggers`, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["triggers", projectId] });
      onClose();
    },
  });

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <PixelFrame style={{ width: "min(520px, 95vw)", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 className="pix-mono" style={{ margin: 0, fontSize: 18 }}>
            {initialTrigger ? "Edit Trigger" : "New Trigger"}
          </h3>
          <PixelButton onClick={onClose}>✕</PixelButton>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Field label="Name">
            <input
              value={form.name}
              onChange={(event) => setField("name", event.target.value)}
              placeholder="Daily crypto scan"
              className="pix-input"
            />
          </Field>

          <Field label="Kind">
            <select
              value={form.kind}
              onChange={(event) => setField("kind", event.target.value as TriggerKind)}
              className="pix-input"
            >
              <option value="cron">Cron</option>
              <option value="webhook">Webhook</option>
              <option value="event">Event</option>
              <option value="manual">Manual</option>
            </select>
          </Field>

          <Field label="Workflow">
            <select
              value={form.workflow_id}
              onChange={(event) => setField("workflow_id", event.target.value)}
              className="pix-input"
            >
              <option value="">— none —</option>
              {workflows.map((workflow) => (
                <option key={workflow.id} value={workflow.id}>
                  {workflow.name}
                </option>
              ))}
            </select>
          </Field>

          <Field label={`Priority (${form.priority})`}>
            <input
              type="range"
              min={1}
              max={10}
              value={form.priority}
              onChange={(event) => setField("priority", Number(event.target.value))}
              style={{ width: "100%" }}
            />
          </Field>

          {form.kind === "cron" && (
            <Field label="Cron Expression">
              <input
                value={form.cron_expression}
                onChange={(event) => setField("cron_expression", event.target.value)}
                placeholder="*/15 * * * *"
                className="pix-input"
              />
              <div className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)", marginTop: 4 }}>
                Examples: */15 * * * * · 0 * * * * · 0 9 * * 1-5
              </div>
            </Field>
          )}

          {form.kind === "webhook" && (
            <Field label="Webhook Path">
              <input
                value={form.webhook_path}
                onChange={(event) => setField("webhook_path", event.target.value)}
                placeholder="project-ingest"
                className="pix-input"
              />
              <div style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center" }}>
                <PixelButton onClick={generateSecret}>Generate Secret</PixelButton>
                {generatedSecret && (
                  <span className="pix-mono" style={{ fontSize: 12, color: "#e7b53c", wordBreak: "break-all" }}>
                    {generatedSecret}
                  </span>
                )}
              </div>
            </Field>
          )}

          {form.kind === "event" && (
            <Field label="Event Filter JSON">
              <textarea
                value={form.filter_json}
                onChange={(event) => setField("filter_json", event.target.value)}
                rows={4}
                placeholder='{"event_type":"run.completed"}'
                className="pix-input pix-mono"
                style={{ resize: "vertical" }}
              />
            </Field>
          )}
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 20, justifyContent: "flex-end" }}>
          <PixelButton onClick={onClose}>Cancel</PixelButton>
          <PixelButton
            variant="green"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || !form.name.trim()}
          >
            {saveMutation.isPending ? "Saving…" : initialTrigger ? "Save Trigger" : "Create Trigger"}
          </PixelButton>
        </div>
        {saveMutation.isError && (
          <div className="pix-mono" style={{ color: "#df5b53", fontSize: 13, marginTop: 8 }}>
            {saveMutation.error instanceof ApiError
              ? saveMutation.error.message
              : "Failed to save trigger."}
          </div>
        )}
      </PixelFrame>
    </div>
  );
}

export default function TriggerRegistryPage() {
  const queryClient = useQueryClient();
  const { projects } = useConsoleData();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [showDialog, setShowDialog] = useState(false);
  const [editingTrigger, setEditingTrigger] = useState<Trigger | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const projectId = selectedProjectId || projects[0]?.id || "";

  const triggersQuery = useQuery<TriggersResponse, ApiError>({
    queryKey: ["triggers", projectId],
    queryFn: () => apiClient.get(`/projects/${projectId}/triggers`),
    enabled: !!projectId,
    retry: false,
  });

  const workflowsQuery = useQuery<WorkflowsResponse, ApiError>({
    queryKey: ["workflows", projectId],
    queryFn: () => apiClient.get(`/projects/${projectId}/workflows`),
    enabled: !!projectId,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ triggerId, isEnabled }: { triggerId: string; isEnabled: boolean }) =>
      apiClient.patch(`/projects/${projectId}/triggers/${triggerId}`, { is_enabled: isEnabled }),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["triggers", projectId] });
    },
    onError: (error) =>
      setActionError(error instanceof ApiError ? error.message : "Failed to update trigger."),
  });

  const deleteMutation = useMutation({
    mutationFn: (triggerId: string) => apiClient.delete(`/projects/${projectId}/triggers/${triggerId}`),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["triggers", projectId] });
    },
    onError: (error) =>
      setActionError(error instanceof ApiError ? error.message : "Failed to delete trigger."),
  });

  const stubMode = triggersQuery.error?.status === 501;
  const triggers = triggersQuery.data?.items ?? [];
  const workflows = workflowsQuery.data?.items ?? [];

  return (
    <>
      <PixelFrame tight>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 10,
          }}
        >
          <div>
            <div className="pix-eyebrow">Hub Management</div>
            <h2 style={{ margin: 0 }}>Trigger Registry</h2>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {projects.length > 0 && (
              <select
                value={projectId}
                onChange={(event) => setSelectedProjectId(event.target.value)}
                className="pix-mono"
                style={{
                  background: "var(--pix-parch2)",
                  border: "2px solid var(--pix-frame)",
                  padding: "4px 8px",
                  fontSize: 14,
                }}
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            )}
            <PixelButton
              variant="green"
              onClick={() => {
                setEditingTrigger(null);
                setShowDialog(true);
              }}
              disabled={!projectId}
            >
              + New Trigger
            </PixelButton>
          </div>
        </div>
      </PixelFrame>

      {stubMode && (
        <PixelFrame>
          <div className="pix-mono" style={{ color: "#e7b53c", fontSize: 13 }}>
            Trigger backend routes are not implemented yet. The UI is wired, but save/edit/delete calls will return 501.
          </div>
        </PixelFrame>
      )}

      {!projectId ? (
        <PixelFrame>
          <div className="pix-empty">No projects yet.</div>
        </PixelFrame>
      ) : (
        <PixelFrame>
          <SectionLabel>Triggers · {triggersQuery.data?.total ?? 0} total</SectionLabel>
          {actionError && (
            <div className="pix-mono" style={{ color: "#df5b53", fontSize: 13, marginBottom: 10 }}>
              {actionError}
            </div>
          )}
          {triggersQuery.isLoading ? (
            <div className="pix-empty">Loading…</div>
          ) : triggersQuery.error && !stubMode ? (
            <div className="pix-empty" style={{ color: "#df5b53" }}>
              {triggersQuery.error.message}
            </div>
          ) : triggers.length === 0 ? (
            <div className="pix-empty">No triggers yet. Create one to automate your workflows.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontFamily: "VT323, monospace",
                  fontSize: 14,
                }}
              >
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--pix-frame)", color: "var(--pix-ink-soft)" }}>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Name</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Kind</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Workflow</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Enabled</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Priority</th>
                    <th style={{ textAlign: "left", padding: "4px 8px" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {triggers.map((trigger) => {
                    const workflow = workflows.find((item) => item.id === trigger.workflow_id);
                    return (
                      <tr key={trigger.id} style={{ borderBottom: "1px solid #4a423840" }}>
                        <td style={{ padding: "6px 8px" }}>{trigger.name}</td>
                        <td style={{ padding: "6px 8px" }}>
                          <KindBadge kind={trigger.kind} />
                        </td>
                        <td style={{ padding: "6px 8px", color: "var(--pix-gold)" }}>
                          {workflow?.name ?? "—"}
                        </td>
                        <td style={{ padding: "6px 8px" }}>
                          <PixelToggle
                            on={trigger.is_enabled}
                            onChange={() =>
                              toggleMutation.mutate({
                                triggerId: trigger.id,
                                isEnabled: !trigger.is_enabled,
                              })
                            }
                          />
                        </td>
                        <td style={{ padding: "6px 8px" }} className="pix-mono">
                          {trigger.priority}
                        </td>
                        <td style={{ padding: "6px 8px" }}>
                          <div style={{ display: "flex", gap: 6 }}>
                            <button
                              className="pix-iconbtn"
                              onClick={() => {
                                setEditingTrigger(trigger);
                                setShowDialog(true);
                              }}
                              title="Edit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              className="pix-iconbtn pix-danger"
                              onClick={() => deleteMutation.mutate(trigger.id)}
                              title="Delete"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </PixelFrame>
      )}

      {showDialog && projectId && (
        <TriggerDialog
          projectId={projectId}
          workflows={workflows}
          initialTrigger={editingTrigger}
          onClose={() => {
            setEditingTrigger(null);
            setShowDialog(false);
          }}
        />
      )}
    </>
  );
}
