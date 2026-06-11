"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Clock } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
  Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui";
import { PixelFrame, PixelButton } from "@/components/pixel-ui";
import { CRON_PRESETS, COMMON_TIMEZONES, describeCron } from "@/lib/cron-helper";

interface Workflow { id: string; key: string; name: string; }
interface Schedule {
  id: string; workflow_id: string; cron_expr: string; timezone: string;
  enabled: boolean; next_run_at: string | null; last_run_at: string | null; last_error_text: string;
}
interface ScheduleList { items: Schedule[]; total: number; }

interface ScheduleManagerProps {
  projectId: string;
  workflows: Workflow[];
}

export function ScheduleManager({ projectId, workflows }: ScheduleManagerProps) {
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState({
    workflow_id: "",
    cron_expr: "0 9 * * *",
    custom_cron: "",
    use_custom: false,
    timezone: "UTC",
  });

  const { data } = useQuery<ScheduleList>({
    queryKey: ["schedules", projectId],
    queryFn: () => apiClient.get(`/projects/${projectId}/schedules`),
  });
  const schedules = data?.items ?? [];
  const wfMap = Object.fromEntries(workflows.map(w => [w.id, w]));

  const createMutation = useMutation({
    mutationFn: () => {
      const wf = workflows.find(w => w.id === form.workflow_id);
      if (!wf) throw new Error("No workflow selected");
      const cron = form.use_custom ? form.custom_cron : form.cron_expr;
      return apiClient.post(`/projects/${projectId}/workflows/${wf.id}/schedules`, {
        cron_expr: cron, timezone: form.timezone,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedules", projectId] });
      toast.success("Schedule created");
      setDialogOpen(false);
    },
    onError: (e: Error) => toast.error(e.message || "Failed to create"),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiClient.patch(`/projects/${projectId}/schedules/${id}`, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules", projectId] }),
    onError: () => toast.error("Failed to update"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/projects/${projectId}/schedules/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedules", projectId] });
      toast.success("Deleted");
      setDeleteId(null);
    },
    onError: () => toast.error("Failed to delete"),
  });

  const formatDate = (iso: string | null) => {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  };

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Clock className="h-4 w-4" style={{ color: "var(--pix-ink-soft)" }} />
          <span className="pix-row-title" style={{ fontSize: 14 }}>Schedules</span>
          <span className="pix-pill">{schedules.length}</span>
        </div>
        <PixelButton variant="gold" onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" /> Add Schedule
        </PixelButton>
      </div>

      {/* Empty state */}
      {schedules.length === 0 ? (
        <PixelFrame>
          <div className="pix-empty">
            <Clock className="mx-auto mb-2 h-8 w-8" />
            No schedules yet
          </div>
        </PixelFrame>
      ) : (
        <div className="space-y-3">
          {schedules.map(s => {
            const wf = wfMap[s.workflow_id];
            const desc = describeCron(s.cron_expr);
            return (
              <PixelFrame key={s.id} tight>
                <div className="pix-row" style={{ alignItems: "center" }}>
                  {/* Toggle */}
                  <button
                    onClick={() => toggleMutation.mutate({ id: s.id, enabled: !s.enabled })}
                    style={{
                      background: s.enabled ? "var(--pix-up)" : "var(--pix-parch-line)",
                      border: "2px solid var(--pix-wood-dark)", width: 36, height: 20,
                      borderRadius: 10, cursor: "pointer", flexShrink: 0, position: "relative",
                      transition: "background 0.2s",
                    }}
                    title={s.enabled ? "Enabled — click to disable" : "Disabled — click to enable"}
                  >
                    <span style={{
                      position: "absolute", top: 2, left: s.enabled ? 16 : 2,
                      width: 12, height: 12, borderRadius: "50%",
                      background: "var(--pix-parch)", transition: "left 0.2s",
                    }} />
                  </button>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span className="pix-row-title">{wf?.name ?? s.workflow_id}</span>
                      <span className="pix-pill pix-gold" style={{ fontFamily: '"VT323",monospace', fontSize: 11 }}>
                        {s.cron_expr}
                      </span>
                      <span className="pix-row-sub">{desc}</span>
                    </div>
                    <div className="pix-row-sub" style={{ marginTop: 2 }}>
                      TZ: {s.timezone} · Next: {formatDate(s.next_run_at)}
                      {s.last_error_text && (
                        <span style={{ color: "var(--pix-red)", marginLeft: 8 }}>
                          {s.last_error_text.slice(0, 50)}
                        </span>
                      )}
                    </div>
                  </div>

                  <button
                    className="pix-iconbtn pix-danger"
                    title="Delete schedule"
                    onClick={() => setDeleteId(s.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </PixelFrame>
            );
          })}
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="pix-root max-w-md"
          style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans",sans-serif', color: "var(--pix-ink)" }}>
              Add Schedule
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="pix-field-label">Workflow</label>
              <Select value={form.workflow_id} onValueChange={v => setForm(f => ({ ...f, workflow_id: v }))}>
                <SelectTrigger style={{ background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                  <SelectValue placeholder="Select workflow…" />
                </SelectTrigger>
                <SelectContent>
                  {workflows.map(w => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="pix-field-label">Schedule</label>
              <Select value={form.use_custom ? "__custom" : form.cron_expr}
                onValueChange={v => {
                  if (v === "__custom") setForm(f => ({ ...f, use_custom: true }));
                  else setForm(f => ({ ...f, cron_expr: v, use_custom: false }));
                }}>
                <SelectTrigger style={{ background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CRON_PRESETS.map(p => (
                    <SelectItem key={p.value} value={p.value}>
                      <span className="font-mono text-xs mr-2">{p.value}</span>
                      <span className="text-muted-foreground text-xs">{p.label}</span>
                    </SelectItem>
                  ))}
                  <SelectItem value="__custom">Custom cron expression…</SelectItem>
                </SelectContent>
              </Select>
              {form.use_custom && (
                <Input className="font-mono text-sm" placeholder="0 9 * * 1-5"
                  value={form.custom_cron}
                  onChange={e => setForm(f => ({ ...f, custom_cron: e.target.value }))}
                  style={{ background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
                />
              )}
              <p className="pix-row-sub" style={{ marginTop: 4 }}>
                {describeCron(form.use_custom ? form.custom_cron : form.cron_expr)}
              </p>
            </div>
            <div className="space-y-1.5">
              <label className="pix-field-label">Timezone</label>
              <Select value={form.timezone} onValueChange={v => setForm(f => ({ ...f, timezone: v }))}>
                <SelectTrigger style={{ background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {COMMON_TIMEZONES.map(tz => <SelectItem key={tz} value={tz}>{tz}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <PixelButton onClick={() => setDialogOpen(false)}>Cancel</PixelButton>
            <PixelButton variant="gold"
              disabled={!form.workflow_id || createMutation.isPending}
              onClick={() => createMutation.mutate()}>
              {createMutation.isPending ? "Scheduling…" : "Schedule"}
            </PixelButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleteId} onOpenChange={(v) => { if (!v) setDeleteId(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete schedule?</AlertDialogTitle>
            <AlertDialogDescription>This will stop the scheduled run permanently.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground"
              onClick={() => deleteId && deleteMutation.mutate(deleteId)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
