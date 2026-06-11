"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export interface ApiAgentTemplate {
  id: string;
  source: string;
  source_key: string | null;
  name: string;
  role: string;
  description: string | null;
  category: string;
  subcategory: string | null;
  default_runtime_kind: string;
  default_model: string;
  default_avatar: string;
  skills: string[];
  tags: string[];
  popularity: number;
  is_active: boolean;
}

export interface AgentTemplate {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  runtime_kind: string;
  tool_permissions: string[];
  max_tokens: number;
  temperature: number;
  memory_type: string;
  tags: string[];
  created_at: string;
  category?: string;
  description?: string | null;
  skills?: string[];
  source?: string;
}

const STORAGE_KEY = "pda_agent_templates";

// Legacy built-in templates (kept as user local templates)
const BUILT_IN_TEMPLATES: AgentTemplate[] = [
  {
    id: "builtin_market_analyst",
    name: "Market Analyst",
    role: "market_analyst",
    system_prompt: "You are a professional market analyst specializing in technical and fundamental analysis. Analyze price action, volume, RSI, MACD, Bollinger Bands, and other indicators. Provide clear buy/sell/hold signals with confidence levels.",
    runtime_kind: "claude-cli",
    tool_permissions: ["web_search", "api_call"],
    max_tokens: 4096,
    temperature: 70,
    memory_type: "long_term",
    tags: ["trading", "finance"],
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "builtin_risk_manager",
    name: "Risk Manager",
    role: "risk_manager",
    system_prompt: "You are a risk management specialist. Evaluate every trade signal for risk/reward ratio, position sizing, max drawdown, and portfolio impact. Approve only trades with R:R >= 2:1 and clear stop-loss levels.",
    runtime_kind: "claude-cli",
    tool_permissions: ["api_call"],
    max_tokens: 2048,
    temperature: 30,
    memory_type: "short_term",
    tags: ["trading", "risk"],
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "builtin_summarizer",
    name: "Summarizer / Secretary",
    role: "summarizer",
    system_prompt: "You are a concise report writer. Transform complex agent outputs into clear, structured summaries. Use bullet points, highlight key decisions, flag urgent items, and present information in order of importance.",
    runtime_kind: "claude-cli",
    tool_permissions: [],
    max_tokens: 2048,
    temperature: 50,
    memory_type: "none",
    tags: ["general", "reporting"],
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "builtin_researcher",
    name: "Web Researcher",
    role: "researcher",
    system_prompt: "You are a thorough web researcher. Search for accurate, up-to-date information on any topic. Verify facts from multiple sources, cite sources, and present findings in a structured format with confidence levels.",
    runtime_kind: "claude-cli",
    tool_permissions: ["web_search"],
    max_tokens: 4096,
    temperature: 40,
    memory_type: "short_term",
    tags: ["general", "research"],
    created_at: "2026-01-01T00:00:00Z",
  },
];

export function useAgentTemplates() {
  const [localTemplates, setLocalTemplates] = useState<AgentTemplate[]>([]);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    let userTemplates: AgentTemplate[] = [];
    if (stored) {
      try {
        userTemplates = JSON.parse(stored) as AgentTemplate[];
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    setLocalTemplates([...BUILT_IN_TEMPLATES, ...userTemplates]);
  }, []);

  const { data: apiTemplates } = useQuery<ApiAgentTemplate[]>({
    queryKey: ["agent-templates"],
    queryFn: () => apiClient.get<ApiAgentTemplate[]>("/agent-templates?limit=500"),
  });

  // Merge API templates (primary) with local templates
  const templates: AgentTemplate[] = [
    ...(apiTemplates ?? []).map((t): AgentTemplate => ({
      id: t.id,
      name: t.name,
      role: t.role,
      system_prompt: "", // fetched on demand via /agent-templates/{id}
      runtime_kind: t.default_runtime_kind || "anthropic-api",
      tool_permissions: [], // default; user can adjust
      max_tokens: 2048,
      temperature: 70,
      memory_type: "none",
      tags: t.tags,
      created_at: "2026-01-01T00:00:00Z",
      category: t.category,
      description: t.description,
      skills: t.skills,
      source: t.source,
    })),
    ...localTemplates.filter((lt) => !(apiTemplates ?? []).some((at) => at.name === lt.name)),
  ];

  const saveTemplate = (template: Omit<AgentTemplate, "id" | "created_at">) => {
    const newTemplate: AgentTemplate = {
      ...template,
      id: `user_${Date.now()}`,
      created_at: new Date().toISOString(),
    };
    const stored = localStorage.getItem(STORAGE_KEY);
    let userTemplates: AgentTemplate[] = [];
    if (stored) {
      try { userTemplates = JSON.parse(stored) as AgentTemplate[]; } catch { /* corrupted */ }
    }
    const updated = [...userTemplates, newTemplate];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    setLocalTemplates((prev) => [...prev, newTemplate]);
    return newTemplate;
  };

  const deleteTemplate = (id: string) => {
    if (id.startsWith("builtin_")) return;
    const stored = localStorage.getItem(STORAGE_KEY);
    let userTemplates: AgentTemplate[] = [];
    if (stored) {
      try { userTemplates = JSON.parse(stored) as AgentTemplate[]; } catch { /* corrupted */ }
    }
    const updated = userTemplates.filter((t) => t.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    setLocalTemplates((prev) => prev.filter((t) => t.id !== id));
  };

  return { templates, saveTemplate, deleteTemplate };
}
