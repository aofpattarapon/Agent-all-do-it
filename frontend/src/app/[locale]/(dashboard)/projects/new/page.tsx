"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { PixelFrame, PixelButton, SectionLabel } from "@/components/pixel-ui";
import { Input, Textarea } from "@/components/ui";

interface Project {
  id: string;
  name: string;
  description: string | null;
}

export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const createMutation = useMutation({
    mutationFn: (body: { name: string; description: string }) =>
      apiClient.post<Project>("/projects", body),
    onSuccess: (project, variables) => {
      // Auto-create default Obsidian vault path for this project
      const slug = variables.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      const defaultVaultPath = `~/Documents/ObsidianVault/${slug || "project"}`;
      localStorage.setItem(`project-vault-path-${project.id}`, defaultVaultPath);
      toast.success("Project created");
      router.push(`/projects/${project.id}`);
    },
    onError: () => toast.error("Failed to create project"),
  });

  const handleCreate = () => {
    if (!name.trim()) return;
    createMutation.mutate({ name: name.trim(), description: description.trim() });
  };

  return (
    <div className="pix-root mx-auto max-w-2xl space-y-4">
      <div>
        <PixelButton onClick={() => router.push("/projects")}>
          <ChevronLeft className="h-4 w-4" /> Projects
        </PixelButton>
      </div>

      <PixelFrame>
        <div style={{ marginBottom: 16 }}>
          <div className="pix-eyebrow">New</div>
          <h2 style={{ fontFamily: '"Pixelify Sans", sans-serif', color: "var(--pix-ink)" }}>Create Project</h2>
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <SectionLabel>Project Name *</SectionLabel>
            <Input
              placeholder="e.g. Document Processor, Trade Bot"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
              autoFocus
              style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
            />
          </div>

          <div className="space-y-1.5">
            <SectionLabel>Description (optional)</SectionLabel>
            <Textarea
              placeholder="What does this project do?"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
            />
          </div>

          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", paddingTop: 8 }}>
            <PixelButton onClick={() => router.push("/projects")}>
              Cancel
            </PixelButton>
            <PixelButton
              variant="gold"
              disabled={!name.trim() || createMutation.isPending}
              onClick={handleCreate}
            >
              {createMutation.isPending ? "Creating…" : "Create Project"}
            </PixelButton>
          </div>
        </div>
      </PixelFrame>
    </div>
  );
}
