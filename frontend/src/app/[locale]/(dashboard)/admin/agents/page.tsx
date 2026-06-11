"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Pencil,
  Trash2,
  Search,
  Bot,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
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
} from "@/components/ui";

interface Project {
  id: string;
  name: string;
}

interface Agent {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  is_active: boolean;
  order_index: number;
  tools_config: Record<string, string>;
  project_id: string;
  project_name?: string;
}

interface AgentList {
  items: Agent[];
  total: number;
}

interface ProjectList {
  items: Project[];
  total: number;
}

const EMPTY_FORM = {
  name: "",
  role: "",
  system_prompt: "",
  order_index: 0,
  ai_backend: "claude-cli",
};

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

export default function AdminAgentsPage() {
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [filterProject, setFilterProject] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Agent | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Agent | null>(null);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const { data: projectsData } = useQuery<ProjectList>({
    queryKey: ["admin-projects-list"],
    queryFn: () => apiClient.get<ProjectList>("/projects?limit=100"),
  });

  // Fetch agents from each project and flatten
  const { data: agentsData, isLoading } = useQuery<{ items: Agent[]; total: number }>({
    queryKey: ["admin-all-agents", filterProject],
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
            .get<AgentList>(`/projects/${p.id}/agents`)
            .then((r) => r.items.map((a) => ({ ...a, project_id: p.id, project_name: p.name }))),
        ),
      );

      const items: Agent[] = results.flatMap((r) => (r.status === "fulfilled" ? r.value : []));
      return { items, total: items.length };
    },
    enabled: !!projectsData,
  });

  const updateAgentMutation = useMutation({
    mutationFn: ({
      projectId,
      agentId,
      body,
    }: {
      projectId: string;
      agentId: string;
      body: Partial<Agent>;
    }) => apiClient.patch<Agent>(`/projects/${projectId}/agents/${agentId}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-all-agents"] });
      toast.success("Agent updated");
      setSheetOpen(false);
      setEditTarget(null);
      setForm(EMPTY_FORM);
    },
    onError: () => toast.error("Failed to update agent"),
  });

  const deleteAgentMutation = useMutation({
    mutationFn: ({ projectId, agentId }: { projectId: string; agentId: string }) =>
      apiClient.delete(`/projects/${projectId}/agents/${agentId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-all-agents"] });
      toast.success("Agent deleted");
      setDeleteTarget(null);
    },
    onError: () => toast.error("Failed to delete agent"),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: async (agents: Agent[]) => {
      await Promise.all(
        agents.map((a) =>
          apiClient.delete(`/projects/${a.project_id}/agents/${a.id}`),
        ),
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-all-agents"] });
      toast.success(`Deleted ${selected.size} agents`);
      setSelected(new Set());
      setBulkDeleteOpen(false);
    },
    onError: () => toast.error("Failed to delete some agents"),
  });

  const toggleAgentActive = (agent: Agent) => {
    updateAgentMutation.mutate({
      projectId: agent.project_id,
      agentId: agent.id,
      body: { is_active: !agent.is_active },
    });
  };

  const filtered = useMemo(() => {
    if (!agentsData?.items) return [];
    if (!search.trim()) return agentsData.items;
    const q = search.toLowerCase();
    return agentsData.items.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.role.toLowerCase().includes(q) ||
        (a.project_name ?? "").toLowerCase().includes(q),
    );
  }, [agentsData?.items, search]);

  const total = agentsData?.total ?? 0;
  const paginated = filtered.slice(page * pageSize, (page + 1) * pageSize);
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));

  const allSelected = paginated.length > 0 && paginated.every((a) => selected.has(a.id));
  const someSelected = paginated.some((a) => selected.has(a.id));

  const toggleAll = () => {
    if (allSelected) {
      setSelected((s) => {
        const next = new Set(s);
        paginated.forEach((a) => next.delete(a.id));
        return next;
      });
    } else {
      setSelected((s) => {
        const next = new Set(s);
        paginated.forEach((a) => next.add(a.id));
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

  const openEdit = (agent: Agent) => {
    setEditTarget(agent);
    setForm({
      name: agent.name,
      role: agent.role,
      system_prompt: agent.system_prompt,
      order_index: agent.order_index,
      ai_backend: agent.tools_config?.ai_backend ?? "claude-cli",
    });
    setSheetOpen(true);
  };

  const handleSave = () => {
    if (!editTarget) return;
    const { ai_backend, ...rest } = form;
    updateAgentMutation.mutate({
      projectId: editTarget.project_id,
      agentId: editTarget.id,
      body: { ...rest, tools_config: { ai_backend } },
    });
  };

  const selectedAgents = useMemo(
    () => (agentsData?.items ?? []).filter((a) => selected.has(a.id)),
    [agentsData?.items, selected],
  );

  const runtimeLabel = (agent: Agent) =>
    agent.tools_config?.ai_backend === "anthropic-api" ? "API" : "CLI";

  return (
    <div className="flex h-full flex-col gap-6">
      {/* Page header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div>
            <p className="text-foreground/55 font-mono text-[11px] tracking-wider uppercase">
              Agents
            </p>
            <h2 className="font-display text-foreground mt-0.5 text-xl font-semibold tracking-tight">
              All agents
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
            placeholder="Search agents…"
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
              <TableHead>Role</TableHead>
              <TableHead className="hidden sm:table-cell">Runtime</TableHead>
              <TableHead className="hidden md:table-cell">Project</TableHead>
              <TableHead>Status</TableHead>
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
              : paginated.map((agent) => (
                  <TableRow key={agent.id} className={selected.has(agent.id) ? "bg-muted/40" : ""}>
                    <TableCell>
                      <Checkbox
                        checked={selected.has(agent.id)}
                        onCheckedChange={() => toggleOne(agent.id)}
                        aria-label={`Select ${agent.name}`}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="bg-primary/10 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg">
                          <Bot className="text-primary h-3.5 w-3.5" />
                        </div>
                        <span className="font-medium">{agent.name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {agent.role}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <Badge
                        variant={
                          agent.tools_config?.ai_backend === "anthropic-api"
                            ? "destructive"
                            : "secondary"
                        }
                        className="text-xs"
                      >
                        {runtimeLabel(agent)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden text-sm md:table-cell">
                      {agent.project_name ?? agent.project_id}
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={agent.is_active}
                        onCheckedChange={() => toggleAgentActive(agent)}
                        aria-label={agent.is_active ? "Disable agent" : "Enable agent"}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          onClick={() => openEdit(agent)}
                          title="Edit"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          onClick={() => setDeleteTarget(agent)}
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
                  {search ? `No agents match "${search}".` : "No agents found."}
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
        <SheetContent side="right" className="w-full max-w-md">
          <SheetHeader>
            <SheetTitle>Edit Agent</SheetTitle>
            <SheetClose onClick={() => setSheetOpen(false)} />
          </SheetHeader>
          <div className="flex flex-col gap-4 p-6">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Name</label>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Researcher"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Role</label>
                <Input
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  placeholder="e.g. researcher"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">AI Backend</label>
              <Select
                value={form.ai_backend}
                onValueChange={(v) => setForm({ ...form, ai_backend: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="claude-cli">Claude CLI (Subscription)</SelectItem>
                  <SelectItem value="anthropic-api">Anthropic API (per token)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">System Prompt</label>
              <Textarea
                rows={6}
                value={form.system_prompt}
                onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                placeholder="Describe what this agent does…"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setSheetOpen(false)}>
                Cancel
              </Button>
              <Button
                disabled={!form.name.trim() || !form.role.trim() || updateAgentMutation.isPending}
                onClick={handleSave}
              >
                {updateAgentMutation.isPending ? "Saving…" : "Save Changes"}
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      {/* Single delete */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete agent?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the agent <strong>{deleteTarget?.name}</strong>.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() =>
                deleteTarget &&
                deleteAgentMutation.mutate({
                  projectId: deleteTarget.project_id,
                  agentId: deleteTarget.id,
                })
              }
            >
              {deleteAgentMutation.isPending ? "Deleting…" : "Delete Agent"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk delete */}
      <AlertDialog open={bulkDeleteOpen} onOpenChange={setBulkDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selected.size} agents?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete {selected.size} agents. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => bulkDeleteMutation.mutate(selectedAgents)}
            >
              {bulkDeleteMutation.isPending ? "Deleting…" : `Delete ${selected.size} Agents`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
