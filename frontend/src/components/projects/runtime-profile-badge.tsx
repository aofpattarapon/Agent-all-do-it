"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Cpu, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";

interface RuntimeProfileData {
  profile: string | null;
  valid_profiles: string[];
}

const PROFILE_STYLES: Record<string, { label: string; classes: string }> = {
  test: {
    label: "TEST",
    classes: "bg-yellow-500/20 text-yellow-300 border border-yellow-500/40 hover:bg-yellow-500/30",
  },
  production: {
    label: "PRODUCTION",
    classes: "bg-green-500/20 text-green-300 border border-green-500/40 hover:bg-green-500/30",
  },
};

const DEFAULT_STYLE = {
  label: "NO PROFILE",
  classes: "bg-zinc-700/40 text-zinc-400 border border-zinc-600/40 hover:bg-zinc-700/60",
};

export function RuntimeProfileBadge({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data } = useQuery<RuntimeProfileData>({
    queryKey: ["runtime-profile", projectId],
    queryFn: () => apiClient.get(`/projects/${projectId}/runtime-profile`),
    staleTime: 30_000,
  });

  const apply = useMutation({
    mutationFn: (profile: string) =>
      apiClient.post(`/projects/${projectId}/runtime-profile`, { profile }),
    onSuccess: (_, profile) => {
      queryClient.invalidateQueries({ queryKey: ["runtime-profile", projectId] });
      queryClient.invalidateQueries({ queryKey: ["agents", projectId] });
      toast.success(`Switched to ${profile.toUpperCase()} profile`);
      setOpen(false);
    },
    onError: () => toast.error("Failed to apply profile"),
  });

  const active = data?.profile ?? null;
  const style = active ? (PROFILE_STYLES[active] ?? DEFAULT_STYLE) : DEFAULT_STYLE;
  const profiles = data?.valid_profiles ?? ["test", "production"];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        disabled={apply.isPending}
        className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs font-mono font-semibold transition-colors ${style.classes}`}
      >
        <Cpu className="h-3 w-3" />
        {style.label}
        <ChevronDown className="h-3 w-3 opacity-60" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-20 mt-1 min-w-[140px] rounded border border-zinc-700 bg-zinc-900 py-1 shadow-lg">
            {profiles.map((p) => {
              const s = PROFILE_STYLES[p] ?? DEFAULT_STYLE;
              const isCurrent = active === p;
              return (
                <button
                  key={p}
                  onClick={() => apply.mutate(p)}
                  disabled={apply.isPending || isCurrent}
                  className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs font-mono transition-colors ${
                    isCurrent
                      ? "cursor-default text-zinc-400"
                      : "text-zinc-300 hover:bg-zinc-800"
                  }`}
                >
                  <span
                    className={`inline-block h-1.5 w-1.5 rounded-full ${
                      p === "production" ? "bg-green-400" : "bg-yellow-400"
                    }`}
                  />
                  {p.toUpperCase()}
                  {isCurrent && <span className="ml-auto text-zinc-500">✓</span>}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
