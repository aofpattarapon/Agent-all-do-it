"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { PixelFrame, SectionLabel } from "@/components/pixel-ui";
import OrderHistoryView from "@/components/trading/OrderHistoryView";

interface Project {
  id: string;
  name: string;
}

interface ProjectList {
  items: Project[];
  total: number;
}

export default function OrderHistoryPage() {
  const { data, isLoading } = useQuery<ProjectList>({
    queryKey: ["projects"],
    queryFn: () => apiClient.get<ProjectList>("/projects"),
  });

  const projects = data?.items ?? [];
  const [selectedId, setSelectedId] = useState<string>("");

  useEffect(() => {
    if (projects.length > 0 && !selectedId) {
      setSelectedId(projects[0]!.id);
    }
  }, [projects, selectedId]);

  return (
    <div className="pix-root mx-auto max-w-7xl space-y-4">
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Trading</div>
            <h2>Order History</h2>
            <p className="pix-row-sub">
              Review executions, positions, journal entries, and performance across your projects.
            </p>
          </div>
          <div className="pix-filters">
            {isLoading ? (
              <span className="pix-muted">Loading projects…</span>
            ) : (
              <select
                className="pix-select"
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      </PixelFrame>

      {selectedId ? (
        <OrderHistoryView projectId={selectedId} />
      ) : (
        <PixelFrame>
          <SectionLabel>Project</SectionLabel>
          <div className="pix-empty">No projects available.</div>
        </PixelFrame>
      )}
    </div>
  );
}
