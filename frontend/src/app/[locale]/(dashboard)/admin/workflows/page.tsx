"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Pencil,
  Trash2,
  Search,
  Workflow,
  ChevronLeft,
  ChevronRight,
  CalendarClock,
  Plus,
  Clock,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { PixelButton } from "@/components/pixel-ui";
import {
  Button,
  Input,
  Textarea,
  Badge,
  Checkbox,
  Skeleton,
  Switch,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetClose,
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogCancel,
  AlertDialogAction,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui";

interface Project {
  id: string;
  name: string;
}

interface WorkflowSchedule {
  id: string;
  cron: string;
  description?: string;
  enabled: boolean;
}

interface Workflow {
  id: string;
  name: string;
  description: string | null;
  trigger: string;
  is_enabled: boolean;
  last_run_at: string | null;
  project_id: string;
  project_name?: string;
  schedules?: WorkflowSchedule[];
}

interface WorkflowList {
  items: Workflow[];
  total: number;
}

interface ProjectList {
  items: Project[];
  total: number;
}

const EMPTY_FORM = { name: "", description: "", trigger: "manual" };
const EMPTY_SCHEDULE = { cron: "", description: "", enabled: true };
const TRIGGER_OPTIONS = ["manual", "webhook", "schedule", "event"];
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

function formatLastRun(iso: string | null): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  const diff = Math.round((Date.now() - d.getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString();
}

export default function AdminWorkflowsPage() {
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [filterProject, setFilterProject] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [sheetOpen, setSheetOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Workflow | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Workflow | null>(null);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const [scheduleTarget, setScheduleTarget] = useState<Workflow | null>(null);
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [scheduleForm, setScheduleForm] = useState(EMPTY_SCHEDULE);
  const [addScheduleOpen, setAddScheduleOpen] = useState(false);

  const { data: projectsData } = useQuery<ProjectList>({
    queryKey: ["admin-projects-list"],
    queryFn: () => apiClient.get<ProjectList>("/projects?limit=100"),
  });

  const { data: workflowsData, isLoading } = useQuery<{ items: Workflow[]; total: number }>({
    queryKey: ["admin-all-workflows", filterProject],
    queryFn: async () => {
      const projects = projectsData?.items ?? [];
      if (projects.length === 0) return { items: [], total: 0 };

      const targets =
        filterProject !== "all"
          ? projects.filter((p) => p.id === filterProject)
          : projects;

      const results = await Promise.allSettled(
        targets.map((p) =>
          apiClient
            .get<WorkflowList>(`/projects/${p.id}/workflows`)
            .then((r) =>
              r.items.map((w) => ({ ...w, project_id: p.id, project_name: p.name })),
            ),
        ),
      );

      const items: Workflow[] = results.flatMap((r) =>
        r.status === "fulfilled" ? r.value : [],
      );
      return { items, total: items.length };
    },
    enabled: !!projectsData,
  });

  const updateWorkflowMutation = useMutation({
    mutationFn: ({
      projectId,
      workflowId,
      body,
    }: {
      projectId: string;
      workflowId: string;
      body: Partial<Workflow>;
    }) => apiClient.patch<Workflow>(`/projects/${projectId}/workflows/${workflowId}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-all-workflows"] });
      toast.success("Workflow updated");
      setSheetOpen(false);
      setEditTarget(null);
      setForm(EMPTY_FORM);
    },
    onError: () => toast.error("Failed to update workflow"),
  });

  const deleteWorkflowMutation = useMutation({
    mutationFn: ({ projectId, workflowId }: { projectId: string; workflowId: string }) =>
      apiClient.delete(`/projects/${projectId}/workflows/${workflowId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-all-workflows"] });
      toast.success("Workflow deleted");
      setDeleteTarget(null);
    },
    onError: () => toast.error("Failed to delete workflow"),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: async (workflows: Workflow[]) => {
      await Promise.all(
        workflows.map((w) =>
          apiClient.delete(`/projects/${w.project_id}/workflows/${w.id}`),
        ),
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-all-workflows"] });
      toast.success(`Deleted ${selected.size} workflows`);
      setSelected(new Set());
      setBulkDeleteOpen(false);
    },
    onError: () => toast.error("Failed to delete some workflows"),
  });

  const addScheduleMutation = useMutation({
    mutationFn: ({
      projectId,
      workflowId,
      body,
    }: {
      projectId: string;
      workflowId: string;
      body: typeof EMPTY_SCHEDULE;
    }) =>
      apiClient.post(`/projects/${projectId}/workflows/${workflowId}/schedules`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-all-workflows"] });
      toast.success("Schedule added");
      setAddScheduleOpen(false);
      setScheduleForm(EMPTY_SCHEDULE);
    },
    onError: () => toast.error("Failed to add schedule"),
  });

  const deleteScheduleMutation = useMutation({
    mutationFn: ({
      projectId,
      workflowId,
      scheduleId,
    }: {
      projectId: string;
      workflowId: string;
      scheduleId: string;
    }) =>
      apiClient.delete(
        `/projects/${projectId}/workflows/${workflowId}/schedules/${scheduleId}`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-all-workflows"] });
      toast.success("Schedule removed");
    },
    onError: () => toast.error("Failed to remove schedule"),
  });

  const toggleEnabled = (workflow: Workflow) => {
    updateWorkflowMutation.mutate({
      projectId: workflow.project_id,
      workflowId: workflow.id,
      body: { is_enabled: !workflow.is_enabled },
    });
  };

  const filtered = useMemo(() => {
    if (!workflowsData?.items) return [];
    if (!search.trim()) return workflowsData.items;
    const q = search.toLowerCase();
    return workflowsData.items.filter(
      (w) =>
        w.name.toLowerCase().includes(q) ||
        (w.project_name ?? "").toLowerCase().includes(q) ||
        w.trigger.toLowerCase().includes(q),
    );
  }, [workflowsData?.items, search]);

  const total = workflowsData?.total ?? 0;
  const paginated = filtered.slice(page * pageSize, (page + 1) * pageSize);
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));

  const allSelected = paginated.length > 0 && paginated.every((w) => selected.has(w.id));
  const someSelected = paginated.some((w) => selected.has(w.id));

  const toggleAll = () => {
    if (allSelected) {
      setSelected((s) => {
        const next = new Set(s);
        paginated.forEach((w) => next.delete(w.id));
        return next;
      });
    } else {
      setSelected((s) => {
        const next = new Set(s);
        paginated.forEach((w) => next.add(w.id));
        return next;
      });
    }
  };

  const toggleOne = (id: string) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const openEdit = (workflow: Workflow) => {
    setEditTarget(workflow);
    setForm({
      name: workflow.name,
      description: workflow.description ?? "",
      trigger: workflow.trigger,
    });
    setSheetOpen(true);
  };

  const openSchedules = (workflow: Workflow) => {
    setScheduleTarget(workflow);
    setScheduleDialogOpen(true);
  };

  const handleSave = () => {
    if (!editTarget) return;
    updateWorkflowMutation.mutate({
      projectId: editTarget.project_id,
      workflowId: editTarget.id,
      body: form,
    });
  };

  const selectedWorkflows = useMemo(
    () => (workflowsData?.items ?? []).filter((w) => selected.has(w.id)),
    [workflowsData?.items, selected],
  );

  return (
    <div className="flex h-full flex-col gap-6">
      {/* Page header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div>
            <p className="text-foreground/55 font-mono text-[11px] tracking-wider uppercase">
              Workflows
            </p>
            <h2 className="font-display text-foreground mt-0.5 text-xl font-semibold tracking-tight">
              All workflows
            </h2>
          </div>
          <Badge variant="secondary" className="font-mono text-xs">
            {total}
          </Badge>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder="Search workflows…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            className="pl-10"
          />
        </div>
        <Select value={filterProject} onValueChange={(v) => { setFilterProject(v); setPage(0); }}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All projects" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All projects</SelectItem>
            {projectsData?.items.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(0); }}>
          <SelectTrigger className="w-[110px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZE_OPTIONS.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n} / page
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selected.size > 0 && (
          <Button size="sm" variant="destructive" onClick={() => setBulkDeleteOpen(true)}>
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Delete {selected.size}
          </Button>
        )}
      </div>

      {/* Table */}
      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  checked={allSelected}
                  data-state={someSelected && !allSelected ? "indeterminate" : undefined}
                  onCheckedChange={toggleAll}
                  aria-label="Select all"
                />
              </TableHead>
              <TableHead>Name</TableHead>
              <TableHead className="hidden md:table-cell">Project</TableHead>
              <TableHead>Trigger</TableHead>
              <TableHead>Enabled</TableHead>
              <TableHead className="hidden sm:table-cell">Last Run</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && paginated.length === 0
              ? Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 7 }).map((__, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : paginated.map((workflow) => (
                  <TableRow
                    key={workflow.id}
                    className={selected.has(workflow.id) ? "bg-muted/40" : ""}
                  >
                    <TableCell>
                      <Checkbox
                        checked={selected.has(workflow.id)}
                        onCheckedChange={() => toggleOne(workflow.id)}
                        aria-label={`Select ${workflow.name}`}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="bg-primary/10 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg">
                          <Workflow className="text-primary h-3.5 w-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium">{workflow.name}</p>
                          {workflow.description && (
                            <p className="text-muted-foreground truncate text-xs">
                              {workflow.description}
                            </p>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden text-sm md:table-cell">
                      {workflow.project_name ?? workflow.project_id}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="capitalize text-xs">
                        {workflow.trigger}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={workflow.is_enabled}
                        onCheckedChange={() => toggleEnabled(workflow)}
                        aria-label={workflow.is_enabled ? "Disable" : "Enable"}
                      />
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden text-sm sm:table-cell">
                      {formatLastRun(workflow.last_run_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 gap-1 px-2 text-xs"
                          onClick={() => openSchedules(workflow)}
                          title="Manage schedules"
                        >
                          <Clock className="h-3 w-3" />
                          <span className="hidden sm:inline">Schedules</span>
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          onClick={() => openEdit(workflow)}
                          title="Edit"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          onClick={() => setDeleteTarget(workflow)}
                          title="Delete"
                        >
                          <Trash2 className="text-destructive h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
            {!isLoading && paginated.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-muted-foreground py-10 text-center">
                  {search ? `No workflows match "${search}".` : "No workflows found."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {filtered.length > 0 && (
        <div className="flex items-center justify-between border-t px-1 pt-3">
          <span className="text-muted-foreground text-sm">
            {page * pageSize + 1}–{Math.min(filtered.length, (page + 1) * pageSize)} of{" "}
            {filtered.length}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-muted-foreground px-2 text-sm">
              {page + 1} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Edit Sheet */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right" className="pix-root w-full max-w-md">
          <SheetHeader>
            <SheetTitle><span style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, color: "var(--pix-ink)" }}>Edit Workflow</span></SheetTitle>
            <SheetClose onClick={() => setSheetOpen(false)} />
          </SheetHeader>
          <div className="flex flex-col gap-4 p-6">
            <div className="space-y-1.5">
              <label className="pix-field-label">Name</label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Workflow name"
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
              />
            </div>
            <div className="space-y-1.5">
              <label className="pix-field-label">Description</label>
              <Textarea
                rows={3}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="What does this workflow do?"
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
              />
            </div>
            <div className="space-y-1.5">
              <label className="pix-field-label">Trigger</label>
              <Select value={form.trigger} onValueChange={(v) => setForm({ ...form, trigger: v })}>
                <SelectTrigger style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TRIGGER_OPTIONS.map((t) => (
                    <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <PixelButton onClick={() => setSheetOpen(false)}>Cancel</PixelButton>
              <PixelButton variant="gold" disabled={!form.name.trim() || updateWorkflowMutation.isPending} onClick={handleSave}>
                {updateWorkflowMutation.isPending ? "Saving…" : "Save Changes"}
              </PixelButton>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      {/* Schedules Dialog */}
      <Dialog open={scheduleDialogOpen} onOpenChange={setScheduleDialogOpen}>
        <DialogContent className="pix-root max-w-lg" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, color: "var(--pix-ink)", display: "flex", alignItems: "center", gap: 8 }}>
              <CalendarClock className="h-4 w-4" />
              Schedules — {scheduleTarget?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {(!scheduleTarget?.schedules || scheduleTarget.schedules.length === 0) && (
              <p className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)", textAlign: "center", padding: "16px 0" }}>
                No schedules configured.
              </p>
            )}
            {scheduleTarget?.schedules?.map((sched) => (
              <div key={sched.id} style={{
                background: "var(--pix-parch-2)", border: "2px solid var(--pix-wood-dark)",
                padding: "10px 14px", display: "flex", alignItems: "center", justifyContent: "space-between",
              }}>
                <div>
                  <p style={{ fontFamily: '"VT323", monospace', fontSize: 15, color: "var(--pix-ink)" }}>{sched.cron}</p>
                  {sched.description && (
                    <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>{sched.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className={"pix-pill " + (sched.enabled ? "pix-completed" : "")} style={{ fontSize: 11 }}>
                    {sched.enabled ? "Active" : "Paused"}
                  </span>
                  <button type="button" className="pix-iconbtn pix-danger"
                    onClick={() => scheduleTarget && deleteScheduleMutation.mutate({
                      projectId: scheduleTarget.project_id, workflowId: scheduleTarget.id, scheduleId: sched.id,
                    })}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
          <DialogFooter>
            <div className="flex gap-2">
              <PixelButton onClick={() => setAddScheduleOpen(true)}>
                <Plus className="h-3.5 w-3.5" /> Add Schedule
              </PixelButton>
              <PixelButton variant="gold" onClick={() => setScheduleDialogOpen(false)}>Done</PixelButton>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Schedule Dialog */}
      <Dialog open={addScheduleOpen} onOpenChange={setAddScheduleOpen}>
        <DialogContent className="pix-root max-w-sm" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, color: "var(--pix-ink)" }}>Add Cron Schedule</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="pix-field-label">Cron Expression</label>
              <Input
                placeholder="e.g. 0 9 * * 1-5"
                value={scheduleForm.cron}
                onChange={(e) => setScheduleForm({ ...scheduleForm, cron: e.target.value })}
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
              />
              <p className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)" }}>
                Standard 5-field cron: min hour day month weekday
              </p>
            </div>
            <div className="space-y-1.5">
              <label className="pix-field-label">Description (optional)</label>
              <Input
                placeholder="e.g. Weekday mornings 9 AM"
                value={scheduleForm.description}
                onChange={(e) => setScheduleForm({ ...scheduleForm, description: e.target.value })}
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={scheduleForm.enabled} onCheckedChange={(v) => setScheduleForm({ ...scheduleForm, enabled: v })} />
              <label className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink)" }}>Enable immediately</label>
            </div>
          </div>
          <DialogFooter>
            <div className="flex gap-2">
              <PixelButton onClick={() => setAddScheduleOpen(false)}>Cancel</PixelButton>
              <PixelButton
                variant="gold"
                disabled={!scheduleForm.cron.trim() || addScheduleMutation.isPending}
                onClick={() => {
                  if (!scheduleTarget) return;
                  addScheduleMutation.mutate({
                    projectId: scheduleTarget.project_id,
                    workflowId: scheduleTarget.id,
                    body: scheduleForm,
                  });
                }}
              >
                {addScheduleMutation.isPending ? "Adding…" : "Add Schedule"}
              </PixelButton>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Single delete */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete workflow?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete <strong>{deleteTarget?.name}</strong> and all its
              schedules and run history. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() =>
                deleteTarget &&
                deleteWorkflowMutation.mutate({
                  projectId: deleteTarget.project_id,
                  workflowId: deleteTarget.id,
                })
              }
            >
              {deleteWorkflowMutation.isPending ? "Deleting…" : "Delete Workflow"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk delete */}
      <AlertDialog open={bulkDeleteOpen} onOpenChange={setBulkDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selected.size} workflows?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete {selected.size} workflows and all their schedules
              and run history. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => bulkDeleteMutation.mutate(selectedWorkflows)}
            >
              {bulkDeleteMutation.isPending
                ? "Deleting…"
                : `Delete ${selected.size} Workflows`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
