"use client";

import type { ReactNode } from "react";
import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CandlestickChart,
  BookOpen,
  BookOpenText,
  Bot,
  ChevronLeft,
  Clock,
  History,
  KeyRound,
  Plug,
  Radio,
  Users,
  Workflow,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { PixelButton, PixelFrame, PixelNavButton } from "@/components/pixel-ui";

interface Project {
  id: string;
  name: string;
  description: string | null;
}

interface ListResponse {
  total: number;
}

type ProjectSectionKey =
  | "agents"
  | "knowledge"
  | "workflows"
  | "schedules"
  | "runs"
  | "trade-floor"
  | "office"
  | "control"
  | "handoffs"
  | "integrations"
  | "secrets"
  | "vault";

interface ProjectSectionShellProps {
  projectId: string;
  activeSection: ProjectSectionKey;
  children: ReactNode;
  maxWidthClassName?: string;
}

export function ProjectSectionShell({
  projectId,
  activeSection,
  children,
  maxWidthClassName = "max-w-7xl",
}: ProjectSectionShellProps) {
  const router = useRouter();

  const { data: project } = useQuery<Project>({
    queryKey: ["project", projectId],
    queryFn: () => apiClient.get<Project>(`/projects/${projectId}`),
  });

  const { data: agentCounts } = useQuery<ListResponse>({
    queryKey: ["agents", projectId, "shell-count"],
    queryFn: () => apiClient.get<ListResponse>(`/projects/${projectId}/agents`),
  });

  const { data: knowledgeCounts } = useQuery<ListResponse>({
    queryKey: ["knowledge", projectId, "shell-count"],
    queryFn: () => apiClient.get<ListResponse>(`/projects/${projectId}/knowledge`),
  });

  const { data: workflowCounts } = useQuery<ListResponse>({
    queryKey: ["workflows", projectId, "shell-count"],
    queryFn: () => apiClient.get<ListResponse>(`/projects/${projectId}/workflows`),
  });

  const { data: runCounts } = useQuery<ListResponse>({
    queryKey: ["runs", projectId, "shell-count"],
    queryFn: () => apiClient.get<ListResponse>(`/projects/${projectId}/runs`),
  });

  const navItems = useMemo(() => ([
    { key: "agents", label: "Agents", icon: <Bot className="h-4 w-4" />, badge: agentCounts?.total ?? 0, href: `/projects/${projectId}` },
    { key: "knowledge", label: "Knowledge", icon: <BookOpen className="h-4 w-4" />, badge: knowledgeCounts?.total ?? 0, href: `/projects/${projectId}#knowledge` },
    { key: "workflows", label: "Workflows", icon: <Workflow className="h-4 w-4" />, badge: workflowCounts?.total ?? 0, href: `/projects/${projectId}#workflows` },
    { key: "schedules", label: "Schedules", icon: <Clock className="h-4 w-4" />, href: `/projects/${projectId}#schedules` },
    { key: "runs", label: "Runs", icon: <History className="h-4 w-4" />, badge: runCounts?.total ?? 0, href: `/projects/${projectId}#runs` },
    { key: "trade-floor", label: "Trade Floor", icon: <CandlestickChart className="h-4 w-4" />, href: `/projects/${projectId}#trade-floor` },
    { key: "office", label: "Office", icon: <Users className="h-4 w-4" />, href: `/projects/${projectId}#office` },
    { key: "control", label: "Control", icon: <Radio className="h-4 w-4" />, href: `/projects/${projectId}#control` },
    { key: "handoffs", label: "Handoffs", icon: <ArrowLeftRight className="h-4 w-4" />, href: `/projects/${projectId}#handoffs` },
    { key: "integrations", label: "Integrations", icon: <Plug className="h-4 w-4" />, href: `/projects/${projectId}#integrations` },
    { key: "secrets", label: "Secrets", icon: <KeyRound className="h-4 w-4" />, href: `/projects/${projectId}#secrets` },
    { key: "vault", label: "Vault", icon: <BookOpenText className="h-4 w-4" />, href: `/projects/${projectId}#vault` },
  ]), [agentCounts?.total, knowledgeCounts?.total, workflowCounts?.total, runCounts?.total, projectId]);

  return (
    <div className={`pix-root mx-auto ${maxWidthClassName} space-y-4`}>
      <PixelButton onClick={() => router.push("/projects")}>
        <ChevronLeft className="h-4 w-4" /> Projects
      </PixelButton>

      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Project</div>
            <h2>{project?.name ?? "Project"}</h2>
            {project?.description ? <p className="pix-row-sub">{project.description}</p> : null}
          </div>
        </div>
      </PixelFrame>

      <div className="pix-tabs">
        {navItems.map((item) => (
          <PixelNavButton
            key={item.key}
            icon={item.icon}
            label={item.label}
            badge={item.badge}
            active={activeSection === item.key}
            onClick={() => router.push(item.href)}
          />
        ))}
      </div>

      {children}
    </div>
  );
}
