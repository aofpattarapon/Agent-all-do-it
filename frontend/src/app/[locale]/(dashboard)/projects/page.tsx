"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Input,
  Textarea,
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui";
import { PixelFrame, PixelButton } from "@/components/pixel-ui";

interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  agent_count?: number;
}

interface ProjectList {
  items: Project[];
  total: number;
}

const EMPTY_FORM = { name: "", description: "" };

export default function ProjectsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [editProject, setEditProject] = useState<Project | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const { data, isLoading } = useQuery<ProjectList>({
    queryKey: ["projects"],
    queryFn: () => apiClient.get<ProjectList>("/projects"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name: string; description: string } }) =>
      apiClient.patch<Project>(`/projects/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project updated");
      setEditProject(null);
      setForm(EMPTY_FORM);
    },
    onError: () => toast.error("Failed to update project"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/projects/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project deleted");
      setDeleteTarget(null);
    },
    onError: () => toast.error("Failed to delete project"),
  });

  const openEdit = (e: React.MouseEvent, project: Project) => {
    e.stopPropagation();
    setForm({ name: project.name, description: project.description ?? "" });
    setEditProject(project);
  };

  const openDelete = (e: React.MouseEvent, project: Project) => {
    e.stopPropagation();
    setDeleteTarget(project);
  };

  const handleUpdate = () => {
    if (!editProject) return;
    updateMutation.mutate({
      id: editProject.id,
      body: { name: form.name.trim(), description: form.description.trim() },
    });
  };

  return (
    <div className="pix-root mx-auto max-w-7xl space-y-4">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div className="pix-eyebrow">Console</div>
          <h2 style={{ fontFamily: '"Pixelify Sans", sans-serif', color: "var(--pix-ink)" }}>Projects</h2>
        </div>
        <PixelButton variant="gold" onClick={() => router.push("/projects/new")}>
          + New Project
        </PixelButton>
      </div>

      {isLoading ? (
        <PixelFrame>
          <div className="pix-empty">Loading projects…</div>
        </PixelFrame>
      ) : data?.items.length === 0 ? (
        <PixelFrame>
          <div className="pix-empty">
            <div style={{ fontSize: 40, marginBottom: 8 }}>🗂️</div>
            No projects yet
            <div style={{ marginTop: 12 }}>
              <PixelButton variant="gold" onClick={() => router.push("/projects/new")}>
                + Create Project
              </PixelButton>
            </div>
          </div>
        </PixelFrame>
      ) : (
        <div className="space-y-3">
          {data?.items.map((project) => (
            <PixelFrame key={project.id} tight onClick={() => router.push(ROUTES.PROJECT_DETAIL(project.id))} style={{ cursor: "pointer" }}>
              <div className="pix-row">
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <span style={{ fontSize: 28 }}>🗂️</span>
                  <div>
                    <div className="pix-row-title">{project.name}</div>
                    <div className="pix-row-sub">{project.description ?? "No description"}</div>
                    <div style={{ fontFamily: '"VT323",monospace', fontSize: 12, color: "var(--pix-ink-soft)", marginTop: 4 }}>
                      {new Date(project.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                  <button className="pix-iconbtn" onClick={(e) => openEdit(e, project)} title="Edit"><Pencil className="h-3.5 w-3.5" /></button>
                  <button className="pix-iconbtn pix-danger" onClick={(e) => openDelete(e, project)} title="Delete"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              </div>
            </PixelFrame>
          ))}
        </div>
      )}

      {/* Edit Dialog */}
      <Dialog open={!!editProject} onOpenChange={(v) => { if (!v) { setEditProject(null); setForm(EMPTY_FORM); } }}>
        <DialogContent className="pix-root max-w-md" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 20, color: "var(--pix-ink)" }}>Edit Project</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="pix-field-label">Name</label>
              <Input
                placeholder="Project name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                autoFocus
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
              />
            </div>
            <div className="space-y-1.5">
              <label className="pix-field-label">Description</label>
              <Textarea
                placeholder="What does this project do?"
                rows={3}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
              />
            </div>
          </div>
          <DialogFooter>
            <div className="flex gap-2">
              <PixelButton onClick={() => { setEditProject(null); setForm(EMPTY_FORM); }}>Cancel</PixelButton>
              <PixelButton
                variant="gold"
                disabled={!form.name.trim() || updateMutation.isPending}
                onClick={handleUpdate}
              >
                {updateMutation.isPending ? "Saving…" : "Save Changes"}
              </PixelButton>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete <strong>{deleteTarget?.name}</strong> and all its agents,
              knowledge documents, and data. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete Project"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
