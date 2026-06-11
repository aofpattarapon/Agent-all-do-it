"use client";

import { useState } from "react";
import { apiClient } from "@/lib/api-client";
import { PixelButton, PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { FolderSync } from "lucide-react";
import { toast } from "sonner";
import { ProjectSectionShell } from "@/components/projects/ProjectSectionShell";

export default function ProjectVaultView({
  projectId,
  embedded = false,
}: {
  projectId: string;
  embedded?: boolean;
}) {
  const vaultBase = process.env.NEXT_PUBLIC_VAULT_BASE_PATH ?? "";
  const [vaultPath, setVaultPath] = useState(vaultBase ? `${vaultBase}/${projectId}` : "");
  const [syncing, setSyncing] = useState(false);

  const handleVaultSync = async () => {
    if (!vaultPath.trim()) return;
    setSyncing(true);
    try {
      const result = await apiClient.post<{ synced?: number; updated?: number; error?: string }>(
        `/projects/${projectId}/vault/sync`,
        { vault_path: vaultPath.trim() },
      );
      if (result?.error) {
        toast.error(result.error);
      } else {
        toast.success(`Synced ${result?.synced ?? 0}, updated ${result?.updated ?? 0}`);
      }
    } catch {
      toast.error("Failed to sync vault");
    } finally {
      setSyncing(false);
    }
  };

  const content = (
    <>
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Obsidian Vault</div>
            <h2>Output & Knowledge Base</h2>
          </div>
        </div>
      </PixelFrame>

      <PixelFrame>
        <SectionLabel>Vault Browser</SectionLabel>
        <div className="pix-mono" style={{ fontSize: 14, color: "var(--pix-muted)", marginBottom: 12 }}>
          Browse and manage Markdown outputs from your agent workflows. Each project has its own vault folder.
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            className="pix-input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Vault path (e.g. /Users/you/Documents/ObsidianVault)"
            value={vaultPath}
            onChange={(e) => setVaultPath(e.target.value)}
          />
          <PixelButton variant="gold" disabled={syncing || !vaultPath.trim()} onClick={handleVaultSync}>
            <FolderSync className="h-4 w-4" />
            {syncing ? "Syncing…" : "Sync Vault"}
          </PixelButton>
        </div>
      </PixelFrame>

      <PixelFrame variant="screen">
        <div className="pix-empty" style={{ color: "#9bdbaa" }}>
          <div style={{ marginBottom: 12 }}>🏛️ Vault Structure</div>
          <pre style={{ textAlign: "left", display: "inline-block", fontSize: 13 }}>
{`outputs/
└── projects/
    └── ${projectId.slice(0, 8)}.../
        ├── 00_index.md
        ├── pm/
        ├── ba/
        ├── sa/
        ├── dev/
        ├── qa/
        ├── handoffs/
        ├── decisions/
        ├── risks/
        └── final/`}
          </pre>
          <div style={{ marginTop: 16 }}>
            Vault files are synced from project knowledge and workflow outputs.
          </div>
        </div>
      </PixelFrame>
    </>
  );

  if (embedded) return <div className="space-y-4">{content}</div>;

  return <ProjectSectionShell projectId={projectId} activeSection="vault">{content}</ProjectSectionShell>;
}
