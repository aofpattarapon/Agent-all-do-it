"use client";

import { use, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Bot, BookOpen, Play, Pencil, Trash2, ChevronLeft, Users, Workflow, Clock, History, Upload, FolderSync, ChevronDown, Check, X, RotateCcw, Copy, Search, Sparkles, ArrowLeftRight, KeyRound, Plug, BookOpenText, Settings2, CandlestickChart, LayoutDashboard, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";
import { PixelFrame, PixelButton, PixelNavButton, SectionLabel } from "@/components/pixel-ui";
import { PixelAvatar } from "@/components/pixel";
import type { SpriteId } from "@/components/pixel";
import { CharacterCreator } from "@/components/pixel-room/character-creator";
import type { CharacterConfig } from "@/components/pixel-room/character-creator";
import { ScheduleManager } from "@/components/schedules/schedule-manager";
import { useAgentTemplates } from "@/hooks/use-agent-templates";
import { useSkills } from "@/hooks/use-skills";
import { useKnowledgeTemplates } from "@/hooks/use-knowledge-templates";
import { ErrorBoundary } from "@/components/error-boundary";
import { DEFAULT_MODEL_VALUE, MODEL_OPTIONS, normalizeRuntimeModel, RUNTIME_OPTIONS, selectableRuntimeModelValue } from "@/lib/runtime-catalog";
import ProjectRoomView from "@/components/projects/project-room-view";
import ProjectHandoffsView from "@/components/projects/project-handoffs-view";
import ProjectIntegrationsView from "@/components/projects/project-integrations-view";
import ProjectSecretsView from "@/components/projects/project-secrets-view";
import ProjectVaultView from "@/components/projects/project-vault-view";
import ProjectTradeFloorView from "@/components/projects/project-trade-floor-view";
import { RuntimeProfileBadge } from "@/components/projects/runtime-profile-badge";
import { WorkboardPage } from "@/components/workboard/WorkboardPage";

interface Project { id: string; name: string; description: string | null; status: string; }
interface AgentConfig {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  is_active: boolean;
  order_index: number;
  tools_config: Record<string, unknown>;
  avatar?: string;
  runtime_kind?: string;
  model?: string;
  tool_permissions?: string[];
  skill_ids?: string[];
  max_tokens?: number;
  temperature?: number;
  memory_type?: string;
  context_window_size?: number;
}
interface AgentList { items: AgentConfig[]; total: number; }
interface KnowledgeDoc { id: string; title: string; content: string; tags: string[]; source_url: string | null; created_at: string; }
interface KnowledgeList { items: KnowledgeDoc[]; total: number; }
interface WorkflowItem { id: string; key: string; name: string; description: string | null; trigger_kind: string; is_enabled: boolean; }
interface WorkflowList { items: WorkflowItem[]; total: number; }
interface RunItem { id: string; status: string; trigger: string; started_at: string | null; finished_at: string | null; output_text: string; error_text?: string; workflow_name?: string; pause_reason?: string; }
interface RunList { items: RunItem[]; total: number; }
interface ScheduleItem { id: string; workflow_id: string; input_payload_json: Record<string, unknown>; enabled: boolean; }
interface ScheduleList { items: ScheduleItem[]; total: number; }


// Pre-made Phaser sprite sheets — must match WORKER_SPRITES in animations.ts
const WORKER_SPRITE_OPTIONS = [
  { key: "character_02", path: "/characters/Premade_Character_48x48_02.png", label: "Alice" },
  { key: "character_03", path: "/characters/Premade_Character_48x48_03.png", label: "Bob" },
  { key: "character_04", path: "/characters/Premade_Character_48x48_04.png", label: "Carol" },
  { key: "character_05", path: "/characters/Premade_Character_48x48_05.png", label: "Dave" },
] as const;

const TOOL_PERMISSION_OPTIONS = [
  { value: "web_search", label: "Web Search" },
  { value: "code_exec", label: "Code Execution" },
  { value: "file_read", label: "File Read" },
  { value: "file_write", label: "File Write" },
  { value: "api_call", label: "API Call" },
  { value: "db_query", label: "DB Query" },
] as const;

const MEMORY_TYPE_OPTIONS = [
  { value: "none", label: "None" },
  { value: "short_term", label: "Short-term" },
  { value: "long_term", label: "Long-term" },
] as const;

interface AgentTask {
  id: string;
  name: string;
  prompt: string;
}

const EMPTY_AGENT = {
  name: "",
  role: "",
  system_prompt: "",
  order_index: 0,
  ai_backend: "claude-cli",
  runtime_kind: "claude-cli",
  model: "",
  fallback_steps: [] as { runtime_kind: string; model: string }[],
  avatar: "character_02" as string,
  tool_permissions: [] as string[],
  skill_ids: [] as string[],
  max_tokens: 2048,
  temperature: 70, // stored ×100 (display value / 100 = 0.7)
  memory_type: "none",
  context_window_size: 10,
  tasks: [] as AgentTask[],
};
const EMPTY_DOC = { title: "", content: "", tags: "", source_url: "" };
const DEFAULT_CHAR_CONFIG: CharacterConfig = {
  baseId: "robot",
  skinTone: "#f4c98f",
  hairColor: "#2d2d2d",
  shirtColor: "#2d3748",
  pantsColor: "#1a202c",
};

const DETAIL_TABS = ["agents", "knowledge", "workflows", "schedules", "runs", "error-log", "trade-floor", "workboard", "office", "handoffs", "integrations", "secrets", "vault"] as const;
type DetailTab = (typeof DETAIL_TABS)[number];

function readTabHash(): DetailTab {
  if (typeof window === "undefined") return "agents";
  const raw = window.location.hash.replace(/^#/, "");
  return DETAIL_TABS.includes(raw as DetailTab) ? (raw as DetailTab) : "agents";
}

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<DetailTab>("agents");
  const [agentDialog, setAgentDialog] = useState<{ open: boolean; editing: AgentConfig | null }>({ open: false, editing: null });
  const [agentForm, setAgentForm] = useState(EMPTY_AGENT);
  const [charConfig, setCharConfig] = useState<CharacterConfig>(DEFAULT_CHAR_CONFIG);
  const [docDialog, setDocDialog] = useState<{ open: boolean; editing: KnowledgeDoc | null }>({ open: false, editing: null });
  const [docForm, setDocForm] = useState(EMPTY_DOC);
  const [search, setSearch] = useState("");
  const [task, setTask] = useState("");
  const [running, setRunning] = useState(false);
  const [viewDoc, setViewDoc] = useState<KnowledgeDoc | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<string[]>([]);
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({});
  const [isDragOver, setIsDragOver] = useState(false);
  const [vaultDialog, setVaultDialog] = useState(false);
  const [vaultPath, setVaultPath] = useState("");
  const [vaultPathInput, setVaultPathInput] = useState("");
  const [editingVaultPath, setEditingVaultPath] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [cloneAgent, setCloneAgent] = useState<AgentConfig | null>(null);
  const [cloneTargetProjectId, setCloneTargetProjectId] = useState("");
  const [allProjects, setAllProjects] = useState<Project[]>([]);
  const [cloningAgent, setCloningAgent] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [newWorkflowDialog, setNewWorkflowDialog] = useState({ open: false, name: "" });
  const [workflowSettings, setWorkflowSettings] = useState<{ open: boolean; workflow: WorkflowItem | null }>({ open: false, workflow: null });
  const [customSkillInput, setCustomSkillInput] = useState("");
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [agentDialogTab, setAgentDialogTab] = useState<"manual" | "template">("manual");
  const [templateSearch, setTemplateSearch] = useState("");
  const [templateCategory, setTemplateCategory] = useState<string>("all");
  const [loadingTemplateId, setLoadingTemplateId] = useState<string | null>(null);
  const [skillDropdownOpen, setSkillDropdownOpen] = useState(false);
  const [catalogDialog, setCatalogDialog] = useState(false);
  const [runFilter, setRunFilter] = useState<"all" | "active" | "completed" | "blocked" | "failed">("active");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mdImportRef = useRef<HTMLInputElement>(null);
  const skillDropdownRef = useRef<HTMLDivElement>(null);

  const selectTab = (nextTab: DetailTab) => {
    setTab(nextTab);
    if (typeof window !== "undefined") {
      const nextHash = nextTab === "agents" ? "" : `#${nextTab}`;
      const nextUrl = `${window.location.pathname}${nextHash}`;
      window.history.replaceState(null, "", nextUrl);
    }
  };

  // Load stored vault path for this project
  useEffect(() => {
    const stored = localStorage.getItem(`project-vault-path-${id}`);
    if (stored) {
      setVaultPath(stored);
      setVaultPathInput(stored);
    }
  }, [id]);

  useEffect(() => {
    const syncFromHash = () => setTab(readTabHash());
    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, []);

  useEffect(() => {
    if (!skillDropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (skillDropdownRef.current && !skillDropdownRef.current.contains(e.target as Node)) {
        setSkillDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [skillDropdownOpen]);

  const { templates, saveTemplate } = useAgentTemplates();
  const { skills, categories: skillCategories } = useSkills();
  const { templates: knowledgeTemplates, categories: knowledgeCategories } = useKnowledgeTemplates();
  const [knowledgeTemplateCategory, setKnowledgeTemplateCategory] = useState<string>("all");
  const [importingTemplateId, setImportingTemplateId] = useState<string | null>(null);

  const { data: templateCategories } = useQuery<string[]>({
    queryKey: ["agent-template-categories"],
    queryFn: () => apiClient.get<string[]>("/agent-templates/categories"),
  });

  const { data: project } = useQuery<Project>({
    queryKey: ["project", id],
    queryFn: () => apiClient.get<Project>(`/projects/${id}`),
  });

  const { data: agents } = useQuery<AgentList>({
    queryKey: ["agents", id],
    queryFn: () => apiClient.get<AgentList>(`/projects/${id}/agents`),
  });

  const { data: runtimeHealth } = useQuery<{ runtimes: { kind: string; available: boolean; detail: string }[] }>({
    queryKey: ["runtime-health"],
    queryFn: () => apiClient.get<{ runtimes: { kind: string; available: boolean; detail: string }[] }>("/health/runtimes"),
    enabled: agentDialog.open,
    staleTime: 30_000,
  });

  const { data: ollamaModels } = useQuery<{ available: boolean; models: string[] }>({
    queryKey: ["ollama-models"],
    queryFn: () => apiClient.get("/health/ollama-models"),
    staleTime: 60_000,
  });

  const { data: docs } = useQuery<KnowledgeList>({
    queryKey: ["knowledge", id, search],
    queryFn: () => apiClient.get<KnowledgeList>(`/projects/${id}/knowledge${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  });

  const { data: workflows } = useQuery<WorkflowList>({
    queryKey: ["workflows", id],
    queryFn: () => apiClient.get<WorkflowList>(`/projects/${id}/workflows`),
  });

  const { data: schedules } = useQuery<ScheduleList>({
    queryKey: ["schedules", id],
    queryFn: () => apiClient.get<ScheduleList>(`/projects/${id}/schedules?limit=100`),
  });

  const { data: runs } = useQuery<RunList>({
    queryKey: ["runs", id],
    queryFn: () => apiClient.get<RunList>(`/projects/${id}/runs?limit=100`),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const hasActive = items.some(r => ["running", "pending", "queued"].includes(r.status));
      return hasActive ? 3000 : false;
    },
  });

  const createWorkflow = useMutation({
    mutationFn: (name: string) =>
      apiClient.post<WorkflowItem>(`/projects/${id}/workflows`, { name, key: name.toLowerCase().replace(/\s+/g, "_"), trigger_kind: "manual" }),
    onSuccess: (wf) => {
      queryClient.invalidateQueries({ queryKey: ["workflows", id] });
      toast.success("Workflow created");
      router.push(`/projects/${id}/workflows/${wf.id}/editor`);
    },
    onError: () => toast.error("Failed to create workflow"),
  });

  const deleteWorkflow = useMutation({
    mutationFn: (wfId: string) => apiClient.delete(`/projects/${id}/workflows/${wfId}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["workflows", id] }); toast.success("Deleted"); },
    onError: () => toast.error("Failed to delete"),
  });

  const updateWorkflowMeta = useMutation({
    mutationFn: ({ wfId, body }: { wfId: string; body: Partial<WorkflowItem> }) =>
      apiClient.patch(`/projects/${id}/workflows/${wfId}`, body),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["workflows", id] }); toast.success("Workflow updated"); },
    onError: () => toast.error("Failed to update workflow"),
  });

  const handleCreateFromTemplate = async (templateId: string) => {
    if (templateId !== "crypto_trading") return;
    setCreatingTemplate(true);
    const definition = {
      steps: [
        { key: "fetch_market", kind: "http_request", label: "Fetch Market Data",
          config: { url: "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=percent_change_24h_desc&per_page=10&page=1", method: "GET" } },
        { key: "market_monitor", kind: "prompt", label: "Market Monitor", agent_key: "market_analyst",
          config: { prompt: "Analyze this market data and identify top 3 crypto trading opportunities. Consider volume, price change, and momentum. Data: {{last_output}}" } },
        { key: "signal_gen", kind: "prompt", label: "Signal Generator", agent_key: "signal_generator",
          config: { prompt: "Generate specific trade signals with entry, TP, SL, and confidence score based on: {{last_output}}" } },
        { key: "risk_check", kind: "prompt", label: "Risk Manager", agent_key: "risk_manager",
          config: { prompt: "Review these signals for risk. Approve or reject each one with reasoning. Signals: {{last_output}}" } },
        { key: "approval_gate", kind: "approval", label: "Approval Gate", config: {} },
        { key: "trade_exec", kind: "prompt", label: "Trade Executor", agent_key: "trade_executor",
          config: { prompt: "Execute these approved signals with exact order details. {{last_output}}" } },
        { key: "portfolio_mon", kind: "prompt", label: "Portfolio Monitor", agent_key: "portfolio_monitor",
          config: { prompt: "Monitor the executed trades and report current P&L. {{last_output}}" } },
        { key: "summarize", kind: "prompt", label: "Summarizer", agent_key: "portfolio_monitor",
          config: { prompt: "Summarize this trading session: what was traded, win/loss, total P&L. {{last_output}}" } },
      ],
      nodes: [
        { id: "start",          type: "start",        position: { x: 50,   y: 200 }, data: { label: "START" } },
        { id: "fetch_market",   type: "http_request",  position: { x: 220,  y: 200 }, data: { label: "Fetch Market", step_key: "fetch_market" } },
        { id: "market_monitor", type: "agent",         position: { x: 420,  y: 200 }, data: { label: "Market Monitor", step_key: "market_monitor" } },
        { id: "signal_gen",     type: "agent",         position: { x: 620,  y: 200 }, data: { label: "Signal Gen", step_key: "signal_gen" } },
        { id: "risk_check",     type: "agent",         position: { x: 820,  y: 200 }, data: { label: "Risk Manager", step_key: "risk_check" } },
        { id: "approval_gate",  type: "approval",      position: { x: 1020, y: 200 }, data: { label: "Approval Gate", step_key: "approval_gate" } },
        { id: "trade_exec",     type: "agent",         position: { x: 1220, y: 200 }, data: { label: "Trade Exec", step_key: "trade_exec" } },
        { id: "portfolio_mon",  type: "agent",         position: { x: 1420, y: 200 }, data: { label: "Portfolio Mon", step_key: "portfolio_mon" } },
        { id: "summarize",      type: "agent",         position: { x: 1620, y: 200 }, data: { label: "Summarizer", step_key: "summarize" } },
        { id: "end",            type: "end",           position: { x: 1820, y: 200 }, data: { label: "END" } },
      ],
      edges: [
        { id: "e1", source: "start",          target: "fetch_market" },
        { id: "e2", source: "fetch_market",   target: "market_monitor" },
        { id: "e3", source: "market_monitor", target: "signal_gen" },
        { id: "e4", source: "signal_gen",     target: "risk_check" },
        { id: "e5", source: "risk_check",     target: "approval_gate" },
        { id: "e6", source: "approval_gate",  target: "trade_exec" },
        { id: "e7", source: "trade_exec",     target: "portfolio_mon" },
        { id: "e8", source: "portfolio_mon",  target: "summarize" },
        { id: "e9", source: "summarize",      target: "end" },
      ],
    };
    try {
      const resp = await apiClient.post<WorkflowItem>(`/projects/${id}/workflows`, {
        name: "Crypto Trading Flow",
        key: "crypto_trading_flow",
        description: "Automated crypto trading: Monitor → Analyze → Signal → Risk → Approval → Execute",
        trigger_kind: "schedule",
        definition_json: definition,
      });
      queryClient.invalidateQueries({ queryKey: ["workflows", id] });
      toast.success("Crypto Trading Flow created!");
      setShowTemplateModal(false);
      if (resp?.id) {
        router.push(`/projects/${id}/workflows/${resp.id}/editor`);
      }
    } catch (err) {
      console.error("Template creation failed", err);
      toast.error("Failed to create workflow from template");
    } finally {
      setCreatingTemplate(false);
    }
  };

  const createAgent = useMutation({
    mutationFn: (body: typeof EMPTY_AGENT) => apiClient.post(`/projects/${id}/agents`, body),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["agents", id] }); toast.success("Agent added"); setAgentDialog({ open: false, editing: null }); setAgentForm(EMPTY_AGENT); },
    onError: () => toast.error("Failed to add agent"),
  });

  const updateAgent = useMutation({
    mutationFn: ({ agentId, body }: { agentId: string; body: Partial<AgentConfig> }) =>
      apiClient.patch(`/projects/${id}/agents/${agentId}`, body),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["agents", id] }); toast.success("Agent updated"); setAgentDialog({ open: false, editing: null }); },
    onError: () => toast.error("Failed to update agent"),
  });

  const deleteAgent = useMutation({
    mutationFn: (agentId: string) => apiClient.delete(`/projects/${id}/agents/${agentId}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["agents", id] }); toast.success("Agent removed"); },
    onError: () => toast.error("Failed to remove agent"),
  });

  const createDoc = useMutation({
    mutationFn: (body: { title: string; content: string; tags: string[]; source_url: string | null }) =>
      apiClient.post(`/projects/${id}/knowledge`, body),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["knowledge", id, search] }); toast.success("Document added"); setDocDialog({ open: false, editing: null }); setDocForm(EMPTY_DOC); },
    onError: () => toast.error("Failed to add document"),
  });

  const updateDoc = useMutation({
    mutationFn: ({ docId, body }: { docId: string; body: Partial<KnowledgeDoc> }) =>
      apiClient.patch(`/projects/${id}/knowledge/${docId}`, body),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["knowledge", id, search] }); toast.success("Document updated"); setDocDialog({ open: false, editing: null }); },
    onError: () => toast.error("Failed to update document"),
  });

  const deleteDoc = useMutation({
    mutationFn: (docId: string) => apiClient.delete(`/projects/${id}/knowledge/${docId}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["knowledge", id, search] }); toast.success("Document deleted"); },
    onError: () => toast.error("Failed to delete document"),
  });

  const runAction = useMutation({
    mutationFn: ({ runId, action }: { runId: string; action: "approve" | "reject" | "retry" }) =>
      apiClient.post(`/projects/${id}/runs/${runId}/${action}`),
    onSuccess: (_data, { action }) => {
      queryClient.invalidateQueries({ queryKey: ["runs", id] });
      toast.success(action === "approve" ? "Run approved" : action === "reject" ? "Run rejected" : "Run retried");
    },
    onError: () => toast.error("Action failed"),
  });

  const handleUploadKnowledge = async (file: File) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/projects/${id}/knowledge/upload`, { method: "POST", body: formData });
      if (!res.ok) throw new Error("upload failed");
      queryClient.invalidateQueries({ queryKey: ["knowledge", id, search] });
      toast.success(`Uploaded "${file.name}"`);
    } catch {
      toast.error("Failed to upload file");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleKnowledgeUpload = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    for (const file of fileArray) {
      setUploadingFiles(prev => [...prev, file.name]);
      const formData = new FormData();
      formData.append("file", file);
      formData.append("source_type", "upload");
      try {
        const res = await fetch(`/api/projects/${id}/knowledge/upload`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) throw new Error("upload failed");
        queryClient.invalidateQueries({ queryKey: ["knowledge", id] });
        toast.success(`Uploaded "${file.name}"`);
      } catch {
        setUploadErrors(prev => ({ ...prev, [file.name]: "Upload failed" }));
      } finally {
        setUploadingFiles(prev => prev.filter(n => n !== file.name));
      }
    }
  };

  const handleAgentKnowledgeUpload = async (agentId: string, files: FileList | File[]) => {
    const fileArray = Array.from(files);
    for (const file of fileArray) {
      setUploadingFiles(prev => [...prev, `${agentId}:${file.name}`]);
      const formData = new FormData();
      formData.append("file", file);
      formData.append("source_type", "upload");
      try {
        const res = await fetch(`/api/projects/${id}/agents/${agentId}/knowledge/upload`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) throw new Error("upload failed");
        toast.success(`Uploaded "${file.name}" to agent`);
      } catch {
        setUploadErrors(prev => ({ ...prev, [`${agentId}:${file.name}`]: "Upload failed" }));
      } finally {
        setUploadingFiles(prev => prev.filter(n => n !== `${agentId}:${file.name}`));
      }
    }
  };

  const handleVaultSync = async (path?: string) => {
    const targetPath = (path ?? vaultPathInput).trim();
    if (!targetPath) return;
    setSyncing(true);
    try {
      const result = await apiClient.post<{ synced?: number; updated?: number; error?: string }>(
        `/projects/${id}/vault/sync`,
        { vault_path: targetPath },
      );
      if (result?.error) {
        toast.error(result.error);
      } else {
        toast.success(`Synced ${result?.synced ?? 0}, updated ${result?.updated ?? 0}`);
        localStorage.setItem(`project-vault-path-${id}`, targetPath);
        setVaultPath(targetPath);
        setVaultPathInput(targetPath);
        queryClient.invalidateQueries({ queryKey: ["knowledge", id, search] });
        setVaultDialog(false);
      }
    } catch {
      toast.error("Failed to sync vault");
    } finally {
      setSyncing(false);
    }
  };

  const openEditAgent = (agent: AgentConfig) => {
    const tc = agent.tools_config as Record<string, string>;
    // Use saved sprite_key, fall back to avatar field, then default
    const spriteKey = tc?.sprite_key ?? tc?.avatar ?? agent.avatar ?? "character_02";
    let tasks: AgentTask[] = [];
    try {
      if (tc?.tasks_json) tasks = JSON.parse(tc.tasks_json) as AgentTask[];
    } catch { /* ignore parse errors */ }
    const runtimeKind = agent.runtime_kind ?? tc?.runtime_kind ?? tc?.ai_backend ?? "claude-cli";
    const normalizedModel = normalizeRuntimeModel(runtimeKind, agent.model ?? "");
    // fallback_chain is stored as a native JSONB array: [{runtime_kind, model}, ...]
    const rawChain = (agent.tools_config as Record<string, unknown>)?.fallback_chain;
    let fallbackSteps: { runtime_kind: string; model: string }[] = [];
    if (Array.isArray(rawChain)) {
      fallbackSteps = (rawChain as { runtime_kind?: string; model?: string }[])
        .filter((e) => e?.runtime_kind)
        .map((e) => ({ runtime_kind: e.runtime_kind!, model: e.model ?? "" }));
    }
    setAgentForm({
      name: agent.name,
      role: agent.role,
      system_prompt: agent.system_prompt,
      order_index: agent.order_index,
      ai_backend: runtimeKind,
      runtime_kind: runtimeKind,
      model: normalizedModel,
      fallback_steps: fallbackSteps,
      avatar: spriteKey,
      tool_permissions: agent.tool_permissions ?? [],
      skill_ids: agent.skill_ids ?? [],
      max_tokens: agent.max_tokens ?? 2048,
      temperature: agent.temperature ?? 70,
      memory_type: agent.memory_type ?? "none",
      context_window_size: agent.context_window_size ?? 10,
      tasks,
    });
    setShowAdvanced(false);
    setAgentDialogTab("manual");
    setAgentDialog({ open: true, editing: agent });
  };

  const openEditDoc = (doc: KnowledgeDoc) => {
    setDocForm({ title: doc.title, content: doc.content, tags: doc.tags.join(", "), source_url: doc.source_url || "" });
    setDocDialog({ open: true, editing: doc });
  };

  const handleRunTask = async () => {
    if (!task.trim()) return;
    setRunning(true);
    try {
      await apiClient.post(`/projects/${id}/run`, { task: task.trim() });
      toast.success("Task started — redirecting to Control Room…", {
        description: `"${task.trim().slice(0, 60)}${task.trim().length > 60 ? "…" : ""}"`,
      });
      router.push(`/projects/${id}#control`);
    } catch {
      toast.error("Failed to run task");
      setRunning(false);
    }
  };

  const openCloneAgent = async (agent: AgentConfig) => {
    setCloneAgent(agent);
    setCloneTargetProjectId("");
    try {
      const result = await apiClient.get<{ items: Project[]; total: number }>("/projects");
      setAllProjects(result.items.filter((p) => p.id !== id));
    } catch {
      setAllProjects([]);
    }
  };

  const handleCloneAgent = async () => {
    if (!cloneAgent || !cloneTargetProjectId) return;
    setCloningAgent(true);
    try {
      const tc = cloneAgent.tools_config as Record<string, string>;
      const payload = {
        name: cloneAgent.name,
        role: cloneAgent.role,
        system_prompt: cloneAgent.system_prompt,
        order_index: cloneAgent.order_index,
        tool_permissions: cloneAgent.tool_permissions ?? [],
        max_tokens: cloneAgent.max_tokens ?? 2048,
        temperature: cloneAgent.temperature ?? 70,
        memory_type: cloneAgent.memory_type ?? "none",
        context_window_size: cloneAgent.context_window_size ?? 10,
        avatar: cloneAgent.avatar ?? "robot",
        model: cloneAgent.model ?? "",
        tools_config: tc,
      };
      await apiClient.post(`/projects/${cloneTargetProjectId}/agents`, payload);
      toast.success(`Agent "${cloneAgent.name}" cloned`);
      setCloneAgent(null);
    } catch {
      toast.error("Failed to clone agent");
    } finally {
      setCloningAgent(false);
    }
  };

  const handleImportMd = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();

    // Parse markdown: look for frontmatter or sections
    // Try YAML frontmatter first: ---\nname: ...\nrole: ...\n---
    const fmMatch = text.match(/^---\n([\s\S]*?)\n---/);
    if (fmMatch) {
      const fm = fmMatch[1] ?? "";
      const nameMatch = fm.match(/^name:\s*(.+)$/m);
      const roleMatch = fm.match(/^role:\s*(.+)$/m);
      const runtimeMatch = fm.match(/^runtime:\s*(.+)$/m);
      const n1 = nameMatch?.[1];
      const r1 = roleMatch?.[1];
      const rt1 = runtimeMatch?.[1];
      if (n1) setAgentForm(f => ({ ...f, name: n1.trim() }));
      if (r1) setAgentForm(f => ({ ...f, role: r1.trim() }));
      if (rt1) setAgentForm(f => ({ ...f, runtime_kind: rt1.trim(), ai_backend: rt1.trim() }));
      // Body after frontmatter = system prompt
      const body = text.slice((fmMatch[0] ?? "").length).trim();
      if (body) setAgentForm(f => ({ ...f, system_prompt: body }));
    } else {
      // No frontmatter: use first line as name (if it's a # heading), rest as system_prompt
      const lines = text.split('\n');
      const firstLine = lines[0] ?? "";
      if (firstLine.startsWith('# ')) {
        setAgentForm(f => ({ ...f, name: firstLine.slice(2).trim(), system_prompt: lines.slice(1).join('\n').trim() }));
      } else {
        // Just use whole content as system_prompt
        setAgentForm(f => ({ ...f, system_prompt: text.trim() }));
      }
    }

    // Reset the file input so the same file can be re-imported
    e.target.value = '';
  };

  const saveAgent = () => {
    const {
      ai_backend,
      runtime_kind,
      avatar,
      tool_permissions,
      max_tokens,
      temperature,
      memory_type,
      context_window_size,
      model,
      fallback_steps,
      tasks,
      ...rest
    } = agentForm;
    // avatar is now a WORKER_SPRITES key (e.g. "character_02")
    const normalizedModel = normalizeRuntimeModel(runtime_kind, model);
    const normalizedSteps = fallback_steps
      .filter((s) => s.runtime_kind)
      .map((s) => {
        const m = normalizeRuntimeModel(s.runtime_kind, s.model);
        return { runtime_kind: s.runtime_kind, model: m === DEFAULT_MODEL_VALUE ? "" : m };
      });
    const payload = {
      ...rest,
      avatar,
      runtime_kind,
      model: normalizedModel === DEFAULT_MODEL_VALUE ? "" : normalizedModel,
      tool_permissions,
      max_tokens,
      temperature, // stored ×100
      memory_type,
      context_window_size,
      tools_config: {
        ai_backend,
        runtime_kind,
        avatar,
        sprite_key: avatar, // used by Phaser room to pick the correct sprite sheet
        ...(normalizedSteps.length > 0 ? { fallback_chain: normalizedSteps } : {}),
        ...(tasks.length > 0 ? { tasks_json: JSON.stringify(tasks) } : {}),
      },
    };
    if (agentDialog.editing) {
      updateAgent.mutate({ agentId: agentDialog.editing.id, body: payload });
    } else {
      createAgent.mutate(payload as unknown as Parameters<typeof createAgent.mutate>[0]);
    }
  };

  const saveDoc = () => {
    const payload = {
      title: docForm.title.trim(),
      content: docForm.content.trim(),
      tags: docForm.tags.split(",").map((t) => t.trim()).filter(Boolean),
      source_url: docForm.source_url.trim() || null,
    };
    if (docDialog.editing) {
      updateDoc.mutate({ docId: docDialog.editing.id, body: payload });
    } else {
      createDoc.mutate(payload);
    }
  };

  return (
    <div className="pix-root mx-auto max-w-7xl space-y-4">
      <ErrorBoundary>
      <div>
        <PixelButton onClick={() => router.push(ROUTES.PROJECTS)}>
          <ChevronLeft className="h-4 w-4" /> Projects
        </PixelButton>
      </div>

      {/* Page header */}
      <PixelFrame>
        <div className="pix-greet">
          <div className="flex-1">
            <div className="pix-eyebrow">Project</div>
            <h2>{project?.name ?? "…"}</h2>
            {project?.description && <p className="pix-row-sub" style={{ marginTop: 4 }}>{project.description}</p>}
          </div>
          {project && <RuntimeProfileBadge projectId={project.id} />}
        </div>
      </PixelFrame>

      {/* Tab strip */}
      <div className="pix-tabs">
        <PixelNavButton icon={<Bot className="h-4 w-4" />} label="Agents" badge={agents?.total ?? 0} active={tab === "agents"} onClick={() => selectTab("agents")} />
        <PixelNavButton icon={<BookOpen className="h-4 w-4" />} label="Knowledge" badge={docs?.total ?? 0} active={tab === "knowledge"} onClick={() => selectTab("knowledge")} />
        <PixelNavButton icon={<Workflow className="h-4 w-4" />} label="Workflows" badge={workflows?.total ?? 0} active={tab === "workflows"} onClick={() => selectTab("workflows")} />
        <PixelNavButton icon={<Clock className="h-4 w-4" />} label="Schedules" active={tab === "schedules"} onClick={() => selectTab("schedules")} />
        <PixelNavButton icon={<History className="h-4 w-4" />} label="Runs" badge={runs?.total ?? 0} active={tab === "runs"} onClick={() => selectTab("runs")} />
        <PixelNavButton icon={<AlertTriangle className="h-4 w-4" />} label="Error Log" badge={(runs?.items ?? []).filter(r => ["paused","blocked","failed","cancelled"].includes(r.status)).length || undefined} active={tab === "error-log"} onClick={() => selectTab("error-log")} />
        <PixelNavButton icon={<CandlestickChart className="h-4 w-4" />} label="Trade Floor" active={tab === "trade-floor"} onClick={() => selectTab("trade-floor")} />
        <PixelNavButton icon={<LayoutDashboard className="h-4 w-4" />} label="Workboard" active={tab === "workboard"} onClick={() => selectTab("workboard")} />
        <PixelNavButton icon={<Users className="h-4 w-4" />} label="Office" active={tab === "office"} onClick={() => selectTab("office")} />
        <PixelNavButton icon={<ArrowLeftRight className="h-4 w-4" />} label="Handoffs" active={tab === "handoffs"} onClick={() => selectTab("handoffs")} />
        <PixelNavButton icon={<Plug className="h-4 w-4" />} label="Integrations" active={tab === "integrations"} onClick={() => selectTab("integrations")} />
        <PixelNavButton icon={<KeyRound className="h-4 w-4" />} label="Secrets" active={tab === "secrets"} onClick={() => selectTab("secrets")} />
        <PixelNavButton icon={<BookOpenText className="h-4 w-4" />} label="Vault" active={tab === "vault"} onClick={() => selectTab("vault")} />
      </div>

      {/* ── Agents Tab ─────────────────────────────────────── */}
      {tab === "agents" && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <PixelButton variant="gold" onClick={() => { setAgentForm(EMPTY_AGENT); setCharConfig(DEFAULT_CHAR_CONFIG); setAgentDialogTab("manual"); setAgentDialog({ open: true, editing: null }); }}>
              <Plus className="h-4 w-4" /> Add Agent
            </PixelButton>
          </div>

          {agents?.items.length === 0 && (
            <PixelFrame>
              <div className="pix-empty">
                <Bot className="mx-auto mb-2 h-8 w-8" />
                No agents yet — add one to get started
              </div>
            </PixelFrame>
          )}

          <div className="space-y-3">
            {agents?.items.map((agent) => {
              const tc = agent.tools_config as Record<string, string>;
              const spriteId = (agent.avatar ?? tc?.avatar ?? "robot") as SpriteId;
              const runtimeKind = agent.runtime_kind ?? tc?.runtime_kind ?? tc?.ai_backend ?? "claude-cli";
              const runtimeLabel =
                runtimeKind === "anthropic-api"
                  ? "API"
                  : runtimeKind === "openai-api"
                    ? "OpenAI"
                    : runtimeKind === "ollama"
                      ? "Ollama"
                      : runtimeKind === "kimi-cli"
                        ? "Kimi"
                        : runtimeKind === "kimi-api"
                          ? "Kimi API"
                          : runtimeKind === "codex-cli"
                            ? "Codex"
                            : "CLI";
              const runtimePillClass =
                runtimeKind === "anthropic-api"
                  ? "pix-pill pix-api"
                  : runtimeKind === "openai-api"
                    ? "pix-pill pix-green-pill"
                    : runtimeKind === "ollama"
                      ? "pix-pill"
                      : runtimeKind === "kimi-cli"
                        ? "pix-pill pix-kimi"
                        : runtimeKind === "kimi-api"
                          ? "pix-pill pix-kimi"
                          : "pix-pill pix-green-pill";
              return (
                <PixelFrame key={agent.id} tight>
                  <div className="pix-row">
                    <div className="flex items-start gap-3">
                      <div className="shrink-0 overflow-hidden" style={{ border: "3px solid var(--pix-wood-dark)", background: "var(--pix-screen-bg)" }}>
                        <PixelAvatar spriteId={spriteId} size={40} />
                      </div>
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="pix-row-title">{agent.name}</span>
                          <span className="pix-pill pix-gold">{agent.role}</span>
                          <span className={runtimePillClass}>{runtimeLabel}</span>
                          {!agent.is_active && <span className="pix-pill">inactive</span>}
                        </div>
                        <p className="pix-row-sub line-clamp-2">{agent.system_prompt}</p>
                      </div>
                    </div>
                    <div className="flex gap-1 shrink-0 items-center flex-wrap">
                      <label style={{ cursor: "pointer", fontFamily: '"VT323",monospace', fontSize: 12,
                        color: "var(--pix-gold)", border: "1px solid var(--pix-gold)", padding: "2px 8px", borderRadius: 2 }}
                        title="Upload knowledge to this agent">
                        + Upload
                        <input type="file" accept=".md,.txt,.pdf" style={{ display: "none" }}
                          onChange={(e) => e.target.files && handleAgentKnowledgeUpload(agent.id, e.target.files)} />
                      </label>
                      <button type="button" className="pix-iconbtn" title="Edit" onClick={() => openEditAgent(agent)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button type="button" className="pix-iconbtn" title="Clone to another project" onClick={() => openCloneAgent(agent)}>
                        <Copy className="h-3.5 w-3.5" />
                      </button>
                      <button type="button" className="pix-iconbtn pix-danger" title="Delete" onClick={() => deleteAgent.mutate(agent.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </PixelFrame>
              );
            })}
          </div>

        </div>
      )}

      {/* ── Knowledge Tab ───────────────────────────────────── */}
      {tab === "knowledge" && (
        <div className="space-y-4">
          {/* Hidden file input for upload button */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.markdown,.txt,.pdf,.docx"
            multiple
            className="hidden"
            onChange={(e) => { if (e.target.files) handleKnowledgeUpload(e.target.files); }}
          />

          {/* Action bar */}
          <div className="flex gap-2 flex-wrap items-center">
            <Input
              placeholder="Search documents…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="max-w-xs"
            />
            <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
              <label style={{
                cursor: "pointer", fontFamily: '"VT323",monospace', fontSize: 14,
                color: "var(--pix-ink)", border: "3px solid var(--pix-wood-dark)",
                padding: "5px 12px", background: "var(--pix-parch-2)", display: "flex", alignItems: "center", gap: 6,
              }}>
                <Upload className="h-3.5 w-3.5" /> Upload File
                <input type="file" accept=".md,.markdown,.txt,.pdf,.docx" multiple style={{ display: "none" }}
                  onChange={(e) => { if (e.target.files) handleKnowledgeUpload(e.target.files); }} />
              </label>
              <PixelButton onClick={() => setCatalogDialog(true)}>
                <BookOpen className="h-3.5 w-3.5" /> Browse Catalog
              </PixelButton>
              <PixelButton variant="gold" onClick={() => { setDocForm(EMPTY_DOC); setDocDialog({ open: true, editing: null }); }}>
                <Plus className="h-4 w-4" /> Add Document
              </PixelButton>
            </div>
          </div>

          {/* Vault path — simple display only */}
          <PixelFrame tight>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", flexShrink: 0 }}>📁 Vault:</span>
              {editingVaultPath ? (
                <>
                  <input
                    value={vaultPathInput}
                    onChange={(e) => setVaultPathInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") { handleVaultSync(); setEditingVaultPath(false); }
                      if (e.key === "Escape") { setVaultPathInput(vaultPath); setEditingVaultPath(false); }
                    }}
                    autoFocus
                    style={{
                      fontFamily: '"VT323", monospace', fontSize: 14, color: "var(--pix-ink)",
                      background: "var(--pix-parch-2)", border: "2px solid var(--pix-gold)",
                      padding: "4px 8px", flex: 1, minWidth: 200, outline: "none",
                    }}
                  />
                  <PixelButton onClick={() => { handleVaultSync(); setEditingVaultPath(false); }} disabled={syncing}>
                    {syncing ? "…" : "Save"}
                  </PixelButton>
                  <PixelButton onClick={() => { setVaultPathInput(vaultPath); setEditingVaultPath(false); }}>
                    Cancel
                  </PixelButton>
                </>
              ) : (
                <>
                  <span style={{
                    fontFamily: '"VT323", monospace', fontSize: 14,
                    color: vaultPath ? "var(--pix-ink)" : "var(--pix-ink-soft)",
                    flex: 1, wordBreak: "break-all",
                  }}>
                    {vaultPath || "Auto-generated when project is created"}
                  </span>
                  <PixelButton onClick={() => { setVaultPathInput(vaultPath); setEditingVaultPath(true); }}>
                    <Pencil className="h-3.5 w-3.5" /> {vaultPath ? "Edit" : "Set Path"}
                  </PixelButton>
                </>
              )}
            </div>
          </PixelFrame>

          {/* Upload progress */}
          {uploadingFiles.length > 0 && (
            <div>
              {uploadingFiles.map(name => (
                <div key={name} style={{ fontFamily: '"VT323",monospace', fontSize: 13,
                  color: "var(--pix-gold)", display: "flex", alignItems: "center", gap: 8, padding: "2px 0" }}>
                  ⏳ Uploading {name.includes(":") ? name.split(":")[1] : name}…
                </div>
              ))}
            </div>
          )}
          {Object.entries(uploadErrors).map(([name, err]) => (
            <div key={name} style={{ fontFamily: '"VT323",monospace', fontSize: 13, color: "#ef4444", padding: "2px 0" }}>
              {name.includes(":") ? name.split(":")[1] : name}: {err}
            </div>
          ))}

          {/* Document list */}
          {docs?.items.length === 0 ? (
            <PixelFrame>
              <div className="pix-empty">
                <BookOpen className="mx-auto mb-2 h-8 w-8" />
                No documents yet — add one or browse the catalog
              </div>
            </PixelFrame>
          ) : (
            <div className="space-y-3">
              {docs?.items.map((doc) => (
                <PixelFrame key={doc.id} tight>
                  <div className="pix-row">
                    <div className="cursor-pointer space-y-1 min-w-0" onClick={() => setViewDoc(doc)}>
                      <p className="pix-row-title hover:underline">{doc.title}</p>
                      <p className="pix-row-sub line-clamp-2">{doc.content}</p>
                      <div className="flex gap-1 flex-wrap">
                        {doc.tags.map((tag) => <span key={tag} className="pix-tag">{tag}</span>)}
                      </div>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button type="button" className="pix-iconbtn" onClick={() => openEditDoc(doc)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button type="button" className="pix-iconbtn pix-danger" onClick={() => deleteDoc.mutate(doc.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </PixelFrame>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Workflows Tab ─────────────────────────────────── */}
      {tab === "workflows" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="pix-row-sub">Visual workflow editor — drag nodes, connect agents, schedule runs.</p>
            <div className="flex gap-2">
              {agents && agents.items.length > 0 && (
                <PixelButton onClick={async () => {
                  // Quick-generate a linear workflow from all active agents
                  const activeAgents = agents.items.filter(a => a.is_active).sort((a, b) => a.order_index - b.order_index);
                  if (activeAgents.length === 0) { toast.error("No active agents to build workflow"); return; }
                  const steps = activeAgents.map((ag, i) => ({
                    key: ag.role || `agent_${i + 1}`,
                    kind: "prompt" as const,
                    label: ag.name,
                    agent_key: ag.role || ag.name,
                    config: { prompt: `Execute your role: ${ag.role}. Context: {{last_output}}` },
                  }));
                  const nodes = [
                    { id: "start", type: "start", position: { x: 50, y: 200 }, data: { label: "START" } },
                    ...activeAgents.map((ag, i) => ({
                      id: ag.id,
                      type: "agent" as const,
                      position: { x: 220 + i * 180, y: 200 },
                      data: { label: ag.name, agent_id: ag.id, agent_name: ag.name, prompt: `Execute your role: ${ag.role}. Context: {{last_output}}` },
                    })),
                    { id: "end", type: "end", position: { x: 220 + activeAgents.length * 180, y: 200 }, data: { label: "END" } },
                  ];
                  const edges = [
                    { id: "e_start", source: "start", target: activeAgents[0]!.id },
                    ...activeAgents.slice(0, -1).map((ag, i) => ({
                      id: `e_${ag.id}`, source: ag.id, target: activeAgents[i + 1]!.id,
                    })),
                    { id: "e_end", source: activeAgents[activeAgents.length - 1]!.id, target: "end" },
                  ];
                  try {
                    const resp = await apiClient.post<WorkflowItem>(`/projects/${id}/workflows`, {
                      name: `${project?.name || "Project"} Flow`,
                      key: `${(project?.name || "project").toLowerCase().replace(/\s+/g, "_")}_flow`,
                      description: `Auto-generated workflow with ${activeAgents.length} agent${activeAgents.length > 1 ? "s" : ""}`,
                      trigger_kind: "manual",
                      definition_json: { version: 1, nodes, edges, steps },
                    });
                    queryClient.invalidateQueries({ queryKey: ["workflows", id] });
                    toast.success(`Workflow "${resp.name}" created with ${activeAgents.length} agents`);
                    if (resp?.id) router.push(`/projects/${id}/workflows/${resp.id}/editor`);
                  } catch {
                    toast.error("Failed to generate workflow");
                  }
                }}>
                  ⚡ Quick Flow
                </PixelButton>
              )}
              <PixelButton onClick={() => setShowTemplateModal(true)}>
                📋 From Template
              </PixelButton>
              <PixelButton variant="gold" onClick={() => setNewWorkflowDialog({ open: true, name: "" })}>
                <Plus className="h-4 w-4" /> New Workflow
              </PixelButton>
            </div>
          </div>
          {!workflows?.items.length ? (
            <PixelFrame>
              <div className="pix-empty">
                <Workflow className="mx-auto mb-2 h-8 w-8" />
                No workflows yet — create one to get started
              </div>
            </PixelFrame>
          ) : (
            <div className="space-y-2">
              {workflows.items.map(wf => (
                <PixelFrame key={wf.id} tight>
                  <div className="pix-row" style={{ alignItems: "center" }}>
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="pix-row-title">{wf.name}</span>
                        <span className="pix-pill pix-gold">{wf.trigger_kind}</span>
                        {!wf.is_enabled && <span className="pix-pill">disabled</span>}
                      </div>
                      {wf.description && <p className="pix-row-sub">{wf.description}</p>}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <PixelButton
                        variant="green"
                        onClick={async () => {
                          try {
                            const matchingSchedule = schedules?.items.find(s => s.workflow_id === wf.id);
                            const input_payload_json = matchingSchedule?.input_payload_json ?? {};
                            await apiClient.post(`/projects/${id}/runs`, { workflow_id: wf.id, trigger: "manual", input_payload_json });
                            toast.success(`"${wf.name}" started`);
                            queryClient.invalidateQueries({ queryKey: ["runs", id] });
                          } catch { toast.error("Failed to start workflow"); }
                        }}
                      >
                        <Play className="h-3.5 w-3.5" /> Run Now
                      </PixelButton>
                      <PixelButton onClick={() => router.push(`/projects/${id}/workflows/${wf.id}/editor`)}>
                        <Workflow className="h-3.5 w-3.5" /> Edit
                      </PixelButton>
                      <button
                        type="button" className="pix-iconbtn"
                        title="Workflow settings"
                        onClick={() => setWorkflowSettings({ open: true, workflow: wf })}
                      >
                        <Settings2 className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button" className="pix-iconbtn pix-danger"
                        onClick={() => {
                          if (confirm(`Delete workflow "${wf.name}"?`)) deleteWorkflow.mutate(wf.id);
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </PixelFrame>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Schedules Tab ─────────────────────────────────── */}
      {tab === "schedules" && (
        <ScheduleManager
          projectId={id}
          workflows={workflows?.items.map(w => ({ id: w.id, key: w.key, name: w.name })) ?? []}
        />
      )}

      {/* ── Runs Tab ──────────────────────────────────────── */}
      {tab === "runs" && (() => {
        const RUN_FILTERS = [
          { key: "active", label: "Active" },
          { key: "completed", label: "Done" },
          { key: "blocked", label: "Blocked" },
          { key: "failed", label: "Errors" },
          { key: "all", label: "All" },
        ] as const;

        const displayedRuns = (runs?.items ?? []).filter(r => {
          if (runFilter === "active") return ["queued", "running", "waiting_approval"].includes(r.status);
          if (runFilter === "completed") return r.status === "completed";
          if (runFilter === "blocked") return r.status === "blocked";
          if (runFilter === "failed") return ["failed", "paused", "cancelled"].includes(r.status);
          return true; // "all"
        });

        return (
          <div className="space-y-4">
            {/* Status filter bar */}
            <div className="flex flex-wrap items-center gap-2">
              {RUN_FILTERS.map(f => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setRunFilter(f.key)}
                  className={`rounded px-3 py-1 text-sm transition-colors ${runFilter === f.key ? "font-bold" : "opacity-60 hover:opacity-100"}`}
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: 14,
                    background: runFilter === f.key ? "var(--pix-wood-dark)" : "transparent",
                    color: runFilter === f.key ? "var(--pix-gold)" : "var(--pix-ink)",
                    border: `1px solid ${runFilter === f.key ? "var(--pix-gold)" : "var(--pix-border)"}`,
                  }}
                >
                  {f.label}
                  {f.key !== "all" && (
                    <span className="ml-1 opacity-60">
                      ({(runs?.items ?? []).filter(r => {
                        if (f.key === "active") return ["queued", "running", "waiting_approval"].includes(r.status);
                        if (f.key === "completed") return r.status === "completed";
                        if (f.key === "blocked") return r.status === "blocked";
                        if (f.key === "failed") return ["failed", "paused", "cancelled"].includes(r.status);
                        return true;
                      }).length})
                    </span>
                  )}
                </button>
              ))}
            </div>

            {!displayedRuns.length ? (
              <PixelFrame>
                <div className="pix-empty">
                  <History className="mx-auto mb-2 h-8 w-8" />
                  {runs?.items.length ? `No ${runFilter} runs` : "No runs yet — run a workflow to see history here"}
                </div>
              </PixelFrame>
            ) : (
              <div className="space-y-2">
                {displayedRuns.map(run => {
                  const statusPill =
                    run.status === "completed"
                      ? "pix-pill pix-completed"
                      : run.status === "blocked"
                        ? "pix-pill pix-blocked"
                      : run.status === "failed"
                        ? "pix-pill pix-failed"
                        : run.status === "waiting_approval"
                          ? "pix-pill pix-gold"
                          : run.status === "paused"
                            ? "pix-pill pix-gold"
                            : run.status === "running"
                              ? "pix-pill pix-completed"
                              : "pix-pill";
                  const pauseInfo = ["paused", "blocked", "failed"].includes(run.status)
                    ? (run.error_text || run.output_text || null)
                    : null;
                  const shortId = run.id.slice(-8);
                  return (
                    <PixelFrame key={run.id} tight>
                      <div className="pix-row" style={{ alignItems: "flex-start" }}>
                        <div className="space-y-1 min-w-0 flex-1">
                          <div className="font-medium truncate" style={{ fontFamily: '"VT323", monospace', fontSize: 15 }}>
                            {run.workflow_name || "Run"}
                            <span className="ml-2 text-xs opacity-40">#{shortId}</span>
                          </div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={statusPill}>{run.status}</span>
                            <span className="pix-pill">{run.trigger}</span>
                            <span className="pix-row-sub">
                              {run.started_at ? new Date(run.started_at).toLocaleString() : "not started"}
                            </span>
                          </div>
                          {pauseInfo && run.pause_reason === "hawk_vote_no_majority" ? (
                            <div className="pix-row-sub space-y-0.5" style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-danger)" }}>
                              {pauseInfo.split("\n").map((line, i) => (
                                <p key={i}>{i === 0 ? `⚠ ${line}` : line}</p>
                              ))}
                            </div>
                          ) : pauseInfo ? (
                            <p className="pix-row-sub line-clamp-2" style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-danger)" }}>
                              ⚠ {pauseInfo.slice(0, 160)}{pauseInfo.length > 160 ? "…" : ""}
                            </p>
                          ) : null}
                          {!pauseInfo && run.output_text && (
                            <p className="pix-row-sub line-clamp-1">{run.output_text.slice(0, 100)}</p>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {run.status === "waiting_approval" && (
                            <>
                              <PixelButton variant="green" disabled={runAction.isPending} onClick={() => runAction.mutate({ runId: run.id, action: "approve" })}>
                                <Check className="h-3.5 w-3.5" /> Approve
                              </PixelButton>
                              <button type="button" className="pix-iconbtn pix-danger" title="Reject" disabled={runAction.isPending} onClick={() => runAction.mutate({ runId: run.id, action: "reject" })}>
                                <X className="h-3.5 w-3.5" /> Reject
                              </button>
                            </>
                          )}
                          {(run.status === "failed" || run.status === "blocked" || run.status === "paused") && (
                            <PixelButton disabled={runAction.isPending} onClick={() => runAction.mutate({ runId: run.id, action: "retry" })}>
                              <RotateCcw className="h-3.5 w-3.5" /> Retry
                            </PixelButton>
                          )}
                          {run.status === "completed" && (
                            <div className="flex gap-2">
                              {(["markdown", "json", "text"] as const).map(fmt => (
                                <a
                                  key={fmt}
                                  href={`/api/projects/${id}/runs/${run.id}/download?format=${fmt}`}
                                  download
                                  className="pix-link"
                                >
                                  .{fmt}
                                </a>
                              ))}
                            </div>
                          )}
                          <button
                            type="button"
                            title="Delete run"
                            className="pix-iconbtn pix-danger"
                            onClick={async () => {
                              if (!confirm("Delete this run permanently?")) return;
                              try {
                                await apiClient.delete(`/projects/${id}/runs/${run.id}`);
                                queryClient.invalidateQueries({ queryKey: ["runs", id] });
                                toast.success("Run deleted");
                              } catch {
                                toast.error("Delete failed");
                              }
                            }}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    </PixelFrame>
                  );
                })}
              </div>
            )}
          </div>
        );
      })()}

      {tab === "error-log" && (() => {
        const errorRuns = (runs?.items ?? []).filter(r => ["paused", "blocked", "failed", "cancelled"].includes(r.status));
        return (
          <div className="space-y-3">
            <PixelFrame tight>
              <div className="px-4 py-2 flex items-center gap-2" style={{ fontFamily: '"VT323", monospace' }}>
                <AlertTriangle className="h-4 w-4" style={{ color: "var(--pix-danger)" }} />
                <span style={{ fontSize: 18 }}>Error Log</span>
                <span className="ml-1 text-xs opacity-60">— paused, blocked, failed and cancelled runs</span>
              </div>
            </PixelFrame>
            {errorRuns.length === 0 ? (
              <PixelFrame>
                <div className="pix-empty">No errors — all clear</div>
              </PixelFrame>
            ) : (
              errorRuns.map(run => {
                const shortId = run.id.slice(-8);
                const ts = run.started_at ? new Date(run.started_at).toLocaleString() : "—";
                const reason = run.error_text || run.output_text || "No details";
                const statusColor = run.status === "paused" ? "var(--pix-gold)" : run.status === "blocked" ? "var(--pix-danger)" : run.status === "failed" ? "var(--pix-danger)" : "var(--pix-muted)";
                return (
                  <PixelFrame key={run.id} tight>
                    <div className="px-4 py-3 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap min-w-0">
                          <span className="font-medium truncate" style={{ fontFamily: '"VT323", monospace', fontSize: 15 }}>
                            {run.workflow_name || "Run"}
                            <span className="ml-1 opacity-40 text-xs">#{shortId}</span>
                          </span>
                          <span className="pix-pill text-xs" style={{ color: statusColor, borderColor: statusColor }}>{run.status}</span>
                          <span className="pix-pill text-xs">{run.trigger}</span>
                          <span className="pix-row-sub text-xs">{ts}</span>
                        </div>
                        <div className="flex shrink-0 gap-2">
                          <PixelButton disabled={runAction.isPending} onClick={() => runAction.mutate({ runId: run.id, action: "retry" })} className="text-xs">
                            <RotateCcw className="h-3 w-3" /> Retry
                          </PixelButton>
                          <button type="button" className="pix-iconbtn pix-danger text-xs" title="Delete" onClick={async () => { try { await apiClient.delete(`/projects/${id}/runs/${run.id}`); queryClient.invalidateQueries({ queryKey: ["runs", id] }); toast.success("Run deleted"); } catch { toast.error("Delete failed"); } }}>
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                      <pre className="text-xs whitespace-pre-wrap break-all opacity-70" style={{ fontFamily: '"VT323", monospace', color: "var(--pix-ink)", maxHeight: 80, overflowY: "auto" }}>
                        {reason.slice(0, 400)}{reason.length > 400 ? "…" : ""}
                      </pre>
                    </div>
                  </PixelFrame>
                );
              })
            )}
          </div>
        );
      })()}

      {tab === "trade-floor" && (
        <ProjectTradeFloorView projectId={id} embedded />
      )}

      {tab === "workboard" && (
        <WorkboardPage projectId={id} />
      )}

      {tab === "office" && (
        <ProjectRoomView projectId={id} embedded />
      )}

      {tab === "handoffs" && (
        <ProjectHandoffsView projectId={id} embedded />
      )}

      {tab === "integrations" && (
        <ProjectIntegrationsView projectId={id} embedded />
      )}

      {tab === "secrets" && (
        <ProjectSecretsView projectId={id} embedded />
      )}

      {tab === "vault" && (
        <ProjectVaultView projectId={id} embedded />
      )}

      {/* ── Agent Dialog ─────────────────────────────────────── */}
      <Dialog open={agentDialog.open} onOpenChange={(v) => setAgentDialog({ open: v, editing: null })}>
        <DialogContent className="pix-root max-w-lg" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 20, letterSpacing: "0.5px", color: "var(--pix-ink)" }}>{agentDialog.editing ? "Edit Agent" : "Add Agent"}</DialogTitle>
          </DialogHeader>

          {/* Tab switcher */}
          <div style={{ display: "flex", gap: 8, marginBottom: 4 }}>
            {(["manual", "template"] as const).map(tabKey => (
              <button key={tabKey} onClick={() => setAgentDialogTab(tabKey)}
                style={{
                  fontFamily: '"Pixelify Sans",sans-serif', fontSize: 13,
                  background: agentDialogTab === tabKey ? "var(--pix-wood-dark)" : "transparent",
                  color: agentDialogTab === tabKey ? "var(--pix-parch)" : "var(--pix-ink)",
                  border: "2px solid var(--pix-wood-dark)", padding: "4px 16px", cursor: "pointer",
                  borderRadius: 2,
                }}>
                {tabKey === "manual" ? "✏️ Manual" : "📋 Template"}
              </button>
            ))}
          </div>

          {/* Template picker */}
          {agentDialogTab === "template" && (
            <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
              {/* Search + Category filters */}
              <div className="flex gap-2 flex-wrap">
                <div className="relative flex-1 min-w-[180px]">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5" style={{ color: "var(--pix-wood-dark)", opacity: 0.6 }} />
                  <Input
                    placeholder="Search templates…"
                    value={templateSearch}
                    onChange={(e) => setTemplateSearch(e.target.value)}
                    className="pl-7"
                    style={{ fontFamily: '"VT323",monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
                  />
                </div>
                <Select value={templateCategory} onValueChange={setTemplateCategory}>
                  <SelectTrigger className="w-[160px]" style={{ fontFamily: '"VT323",monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                    <SelectValue placeholder="All categories" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All categories</SelectItem>
                    {templateCategories?.map((cat) => (
                      <SelectItem key={cat} value={cat}>{cat}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                {templates
                  .filter((tmpl) => {
                    const matchesSearch = !templateSearch ||
                      tmpl.name.toLowerCase().includes(templateSearch.toLowerCase()) ||
                      tmpl.role.toLowerCase().includes(templateSearch.toLowerCase()) ||
                      (tmpl.description ?? "").toLowerCase().includes(templateSearch.toLowerCase()) ||
                      tmpl.tags.some((t) => t.toLowerCase().includes(templateSearch.toLowerCase()));
                    const matchesCategory = templateCategory === "all" || tmpl.category === templateCategory;
                    return matchesSearch && matchesCategory;
                  })
                  .map((tmpl) => (
                    <div
                      key={tmpl.id}
                      onClick={async () => {
                        setLoadingTemplateId(tmpl.id);
                        try {
                          let systemPrompt = "";
                          // If it's a backend template (UUID-like), fetch full details
                          if (tmpl.id.length === 36 && tmpl.id.includes("-")) {
                            const full = await apiClient.get<{ system_prompt: string; default_tool_permissions?: string[]; default_tools_config?: Record<string, string> }>(`/agent-templates/${tmpl.id}`);
                            systemPrompt = full.system_prompt;
                          } else {
                            systemPrompt = (tmpl as { system_prompt?: string }).system_prompt ?? "";
                          }
                          setAgentForm((f) => ({
                            ...f,
                            name: tmpl.name,
                            role: tmpl.role,
                            system_prompt: systemPrompt,
                            runtime_kind: tmpl.runtime_kind || "anthropic-api",
                            ai_backend: tmpl.runtime_kind || "anthropic-api",
                            model: (tmpl as { model?: string }).model ?? "",
                            tool_permissions: (tmpl as { tool_permissions?: string[] }).tool_permissions ?? [],
                            max_tokens: (tmpl as { max_tokens?: number }).max_tokens ?? 2048,
                            temperature: (tmpl as { temperature?: number }).temperature ?? 70,
                            memory_type: (tmpl as { memory_type?: string }).memory_type ?? "none",
                            context_window_size: 10,
                          }));
                          setAgentDialogTab("manual");
                        } catch {
                          toast.error("Failed to load template details");
                        } finally {
                          setLoadingTemplateId(null);
                        }
                      }}
                      style={{
                        cursor: "pointer",
                        padding: "10px 12px",
                        background: "var(--pix-parch-2)",
                        border: loadingTemplateId === tmpl.id ? "2px solid var(--pix-gold)" : "2px solid var(--pix-wood-dark)",
                        borderRadius: 3,
                        fontFamily: '"Pixelify Sans",sans-serif',
                        opacity: loadingTemplateId === tmpl.id ? 0.7 : 1,
                      }}
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        <span style={{ fontWeight: 600, color: "var(--pix-ink)", fontSize: 14 }}>{tmpl.name}</span>
                        {tmpl.category && (
                          <span className="pix-pill pix-gold" style={{ fontSize: 10, padding: "1px 6px" }}>
                            {tmpl.category}
                          </span>
                        )}
                        {tmpl.source && tmpl.source !== "user" && (
                          <span className="pix-pill" style={{ fontSize: 10, padding: "1px 6px" }}>
                            {tmpl.source === "agency" ? "🎭 Agency" : tmpl.source === "500-ai" ? "🤖 500-AI" : tmpl.source}
                          </span>
                        )}
                        {loadingTemplateId === tmpl.id && <Sparkles className="h-3 w-3 animate-spin" style={{ color: "var(--pix-gold)" }} />}
                      </div>
                      <div style={{ fontSize: 12, fontFamily: '"VT323",monospace', color: "var(--pix-ink)", opacity: 0.85, marginTop: 2 }}>
                        {tmpl.role}
                        {tmpl.skills && tmpl.skills.length > 0 && ` · ${tmpl.skills.slice(0, 4).join(", ")}`}
                      </div>
                      {tmpl.description && (
                        <div style={{ fontSize: 11, color: "var(--pix-ink)", opacity: 0.7, marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "100%" }}>
                          {tmpl.description}
                        </div>
                      )}
                    </div>
                  ))}
                {templates.filter((tmpl) => {
                  const matchesSearch = !templateSearch ||
                    tmpl.name.toLowerCase().includes(templateSearch.toLowerCase()) ||
                    tmpl.role.toLowerCase().includes(templateSearch.toLowerCase()) ||
                    (tmpl.description ?? "").toLowerCase().includes(templateSearch.toLowerCase()) ||
                    tmpl.tags.some((t) => t.toLowerCase().includes(templateSearch.toLowerCase()));
                  const matchesCategory = templateCategory === "all" || tmpl.category === templateCategory;
                  return matchesSearch && matchesCategory;
                }).length === 0 && (
                  <div className="pix-empty" style={{ padding: 24 }}>
                    <Search className="mx-auto mb-2 h-6 w-6" />
                    No templates match your filters
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1" style={{ display: agentDialogTab === "template" ? "none" : undefined }}>
            {/* Sprite picker — 4 pre-made characters that appear in the Office room */}
            <div>
              <label className="pix-field-label">Character (shown in Office)</label>
              <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
                {WORKER_SPRITE_OPTIONS.map((ws) => {
                  const isSelected = agentForm.avatar === ws.key;
                  return (
                    <button
                      key={ws.key}
                      type="button"
                      onClick={() => setAgentForm((f) => ({ ...f, avatar: ws.key }))}
                      style={{
                        padding: 4, cursor: "pointer", border: isSelected ? "3px solid var(--pix-gold)" : "3px solid var(--pix-wood-dark)",
                        background: isSelected ? "rgba(201,162,39,0.15)" : "var(--pix-parch-2)",
                        borderRadius: 3, display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                        transition: "all 0.1s",
                      }}
                      title={ws.label}
                    >
                      {/* Sprite thumbnail — shows the first idle-down frame via CSS background-position */}
                      <div style={{
                        width: 48, height: 96, overflow: "hidden",
                        backgroundImage: `url('${ws.path}')`,
                        backgroundSize: `${56 * 48}px auto`,
                        backgroundPosition: `${-18 * 48}px ${-1 * 96}px`, // row 1, col 18 = idle-down
                        imageRendering: "pixelated",
                        flexShrink: 0,
                      }} />
                      <span style={{ fontFamily: '"VT323",monospace', fontSize: 13, color: "var(--pix-ink)", letterSpacing: 0.5 }}>
                        {ws.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="pix-field-label">Name</label>
                <Input placeholder="e.g. Researcher" value={agentForm.name} onChange={(e) => setAgentForm({ ...agentForm, name: e.target.value })} style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }} />
              </div>
              <div className="space-y-1.5">
                <label className="pix-field-label">Role</label>
                <Input placeholder="e.g. researcher" value={agentForm.role} onChange={(e) => setAgentForm({ ...agentForm, role: e.target.value })} style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }} />
              </div>
            </div>

            {/* Runtime Kind */}
            <div className="space-y-1.5">
              <label className="pix-field-label">Runtime</label>
              <Select
                value={agentForm.runtime_kind}
                onValueChange={(v) => setAgentForm({ ...agentForm, runtime_kind: v, ai_backend: v, model: "" })}
              >
                <SelectTrigger style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RUNTIME_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      <div className="flex flex-col">
                        <span>{opt.label}</span>
                        <span className="text-muted-foreground text-xs">{opt.description}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {/* Runtime health indicator */}
              {runtimeHealth?.runtimes && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                  {runtimeHealth.runtimes.map((rt) => {
                    const selected = rt.kind === agentForm.runtime_kind;
                    return (
                      <div
                        key={rt.kind}
                        title={rt.detail}
                        style={{
                          fontFamily: '"VT323", monospace',
                          fontSize: 11,
                          padding: "2px 8px",
                          borderRadius: 2,
                          border: `2px solid ${selected ? "var(--pix-gold)" : rt.available ? "#9ec79e" : "#e0b1ad"}`,
                          background: selected ? "rgba(201,162,39,0.15)" : rt.available ? "#e2efd5" : "#f4dedb",
                          color: selected ? "var(--pix-wood-darkest)" : rt.available ? "var(--pix-green-dark)" : "var(--pix-red)",
                          cursor: "default",
                        }}
                      >
                        {rt.available ? "●" : "○"} {rt.kind}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Model */}
            <div className="space-y-1.5">
              <label className="pix-field-label">Model</label>
              <Select
                key={`model-select-${agentForm.runtime_kind}`}
                value={agentForm.model || DEFAULT_MODEL_VALUE}
                onValueChange={(v) => setAgentForm({ ...agentForm, model: v === DEFAULT_MODEL_VALUE ? "" : v })}
              >
                <SelectTrigger style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {agentForm.runtime_kind === "ollama"
                    ? (ollamaModels?.models ?? []).length > 0
                      ? (ollamaModels!.models).map((m) => (
                          <SelectItem key={m} value={m}>{m}</SelectItem>
                        ))
                      : <SelectItem value="" disabled>No models — check Ollama URL in Admin → Settings</SelectItem>
                    : (MODEL_OPTIONS[agentForm.runtime_kind || "claude-cli"] || []).map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))
                  }
                </SelectContent>
              </Select>
            </div>

            {/* Fallback chain — up to 3 steps */}
            <div style={{ border: "2px dashed var(--pix-wood-dark)", padding: "10px 12px", background: "var(--pix-parch-2)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 13, color: "var(--pix-ink)", fontWeight: 600 }}>
                  Fallback chain (if primary fails)
                </span>
                {agentForm.fallback_steps.length < 3 && (
                  <button
                    type="button"
                    onClick={() => setAgentForm((f) => ({ ...f, fallback_steps: [...f.fallback_steps, { runtime_kind: "", model: "" }] }))}
                    style={{
                      fontFamily: '"VT323",monospace', fontSize: 13, cursor: "pointer",
                      padding: "2px 10px", borderRadius: 2,
                      background: "var(--pix-gold)", color: "var(--pix-wood-darkest)",
                      border: "2px solid var(--pix-gold-dark)",
                    }}
                  >
                    + Add Step
                  </button>
                )}
              </div>

              {agentForm.fallback_steps.length === 0 && (
                <p style={{ fontFamily: '"VT323",monospace', fontSize: 12, color: "var(--pix-ink-soft)" }}>
                  No fallback — agent stops on primary failure. Add up to 3 steps.
                </p>
              )}

              {agentForm.fallback_steps.map((step, idx) => (
                <div key={idx} style={{ marginBottom: idx < agentForm.fallback_steps.length - 1 ? 12 : 0 }}>
                  {/* Step header */}
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ fontFamily: '"VT323",monospace', fontSize: 13, color: "var(--pix-ink-soft)" }}>
                      Step {idx + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => setAgentForm((f) => ({ ...f, fallback_steps: f.fallback_steps.filter((_, i) => i !== idx) }))}
                      style={{
                        fontFamily: '"VT323",monospace', fontSize: 12, cursor: "pointer",
                        padding: "1px 7px", borderRadius: 2,
                        background: "transparent", color: "var(--pix-red, #c44)",
                        border: "2px solid var(--pix-red, #c44)",
                      }}
                    >
                      Remove
                    </button>
                  </div>

                  {/* Runtime pills */}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: step.runtime_kind ? 8 : 0 }}>
                    {RUNTIME_OPTIONS.map((opt) => {
                      const active = step.runtime_kind === opt.value;
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          title={opt.description}
                          onClick={() => setAgentForm((f) => ({
                            ...f,
                            fallback_steps: f.fallback_steps.map((s, i) => i === idx ? { runtime_kind: opt.value, model: "" } : s),
                          }))}
                          style={{
                            fontFamily: '"VT323",monospace', fontSize: 13, cursor: "pointer",
                            padding: "3px 10px", borderRadius: 2,
                            background: active ? "var(--pix-wood-dark)" : "var(--pix-parch)",
                            color: active ? "var(--pix-parch)" : "var(--pix-ink)",
                            border: `2px solid ${active ? "var(--pix-wood-darkest)" : "var(--pix-wood-dark)"}`,
                            transition: "all 0.1s",
                          }}
                        >
                          {active ? "✓ " : ""}{opt.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* Model dropdown — only when runtime is chosen */}
                  {step.runtime_kind && (
                    <Select
                      key={`fb-model-${idx}-${step.runtime_kind}`}
                      value={selectableRuntimeModelValue(step.runtime_kind, step.model)}
                      onValueChange={(v) => setAgentForm((f) => ({
                        ...f,
                        fallback_steps: f.fallback_steps.map((s, i) => i === idx ? { ...s, model: v === DEFAULT_MODEL_VALUE ? "" : v } : s),
                      }))}
                    >
                      <SelectTrigger style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                        <SelectValue placeholder="Default model" />
                      </SelectTrigger>
                      <SelectContent>
                        {step.runtime_kind === "ollama"
                          ? (ollamaModels?.models ?? []).length > 0
                            ? (ollamaModels!.models).map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)
                            : <SelectItem value="" disabled>No models — check Ollama URL</SelectItem>
                          : (MODEL_OPTIONS[step.runtime_kind] || []).map((opt) => (
                              <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                            ))
                        }
                      </SelectContent>
                    </Select>
                  )}

                  {/* Divider between steps */}
                  {idx < agentForm.fallback_steps.length - 1 && (
                    <div style={{ borderTop: "1px dashed var(--pix-wood-dark)", marginTop: 12 }} />
                  )}
                </div>
              ))}
            </div>

            {/* Skills & Permissions — toggle-tag pills */}
            <div>
              <label className="pix-field-label">Skills &amp; Permissions</label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {[...TOOL_PERMISSION_OPTIONS.map(o => ({ value: o.value, label: o.label })),
                  ...agentForm.tool_permissions
                    .filter(p => !TOOL_PERMISSION_OPTIONS.some(o => o.value === p))
                    .map(p => ({ value: p, label: p }))
                ].map((opt) => {
                  const active = agentForm.tool_permissions.includes(opt.value);
                  return (
                    <button key={opt.value} type="button"
                      onClick={() => setAgentForm(f => ({
                        ...f,
                        tool_permissions: active
                          ? f.tool_permissions.filter(p => p !== opt.value)
                          : [...f.tool_permissions, opt.value],
                      }))}
                      style={{
                        fontFamily: '"VT323",monospace', fontSize: 13, cursor: "pointer",
                        padding: "3px 10px", borderRadius: 2,
                        background: active ? "var(--pix-wood-dark)" : "var(--pix-parch-2)",
                        color: active ? "var(--pix-parch)" : "var(--pix-ink)",
                        border: `2px solid ${active ? "var(--pix-wood-darkest)" : "var(--pix-wood-dark)"}`,
                        transition: "all 0.1s",
                      }}>
                      {active ? "✓ " : ""}{opt.label}
                    </button>
                  );
                })}
                {/* Add custom skill */}
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input
                    placeholder="+ custom skill"
                    value={customSkillInput}
                    onChange={(e) => setCustomSkillInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && customSkillInput.trim()) {
                        const key = customSkillInput.trim().toLowerCase().replace(/\s+/g, "_");
                        setAgentForm(f => ({ ...f, tool_permissions: [...f.tool_permissions, key] }));
                        setCustomSkillInput("");
                      }
                    }}
                    style={{
                      fontFamily: '"VT323",monospace', fontSize: 13, width: 100,
                      background: "var(--pix-parch-2)", border: "2px solid var(--pix-wood-dark)",
                      color: "var(--pix-ink)", padding: "3px 6px", outline: "none",
                    }}
                  />
                </div>
              </div>
              <p style={{ fontFamily: '"VT323",monospace', fontSize: 11, color: "var(--pix-ink-soft)", marginTop: 4 }}>
                Click to toggle · type a custom skill + Enter
              </p>
            </div>

            {/* Skill Catalog — multi-select dropdown */}
            <div>
              <label className="pix-field-label">Skill Catalog</label>
              <div ref={skillDropdownRef} style={{ position: "relative", marginTop: 6 }}>
                <button
                  type="button"
                  onClick={() => setSkillDropdownOpen((o) => !o)}
                  style={{
                    width: "100%", textAlign: "left", cursor: "pointer",
                    fontFamily: '"VT323",monospace', fontSize: 14,
                    padding: "6px 10px",
                    background: "var(--pix-parch-2)",
                    border: "2px solid var(--pix-wood-dark)",
                    color: "var(--pix-ink)",
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                  }}
                >
                  <span>
                    {agentForm.skill_ids.length === 0
                      ? "Select skills…"
                      : `${agentForm.skill_ids.length} skill${agentForm.skill_ids.length > 1 ? "s" : ""} selected`}
                  </span>
                  <ChevronDown className={`h-4 w-4 transition-transform ${skillDropdownOpen ? "rotate-180" : ""}`} />
                </button>
                {skillDropdownOpen && (
                  <div style={{
                    position: "absolute", top: "calc(100% + 2px)", left: 0, right: 0, zIndex: 50,
                    background: "var(--pix-parch)", border: "2px solid var(--pix-wood-dark)",
                    maxHeight: 260, overflowY: "auto",
                    boxShadow: "4px 4px 0 rgba(0,0,0,0.25)",
                  }}>
                    {skillCategories.map((cat) => {
                      const catSkills = skills.filter((s) => s.category === cat);
                      if (catSkills.length === 0) return null;
                      return (
                        <div key={cat}>
                          <div style={{
                            fontFamily: '"VT323",monospace', fontSize: 11,
                            color: "var(--pix-ink-soft)", padding: "5px 10px 3px",
                            background: "var(--pix-parch-2)",
                            borderBottom: "1px solid var(--pix-parch-line)",
                            textTransform: "uppercase", letterSpacing: "0.05em",
                          }}>
                            {cat}
                          </div>
                          {catSkills.map((skill) => {
                            const active = agentForm.skill_ids.includes(skill.id);
                            return (
                              <button
                                key={skill.id}
                                type="button"
                                title={skill.description ?? skill.name}
                                onClick={() => setAgentForm((f) => ({
                                  ...f,
                                  skill_ids: active
                                    ? f.skill_ids.filter((sid) => sid !== skill.id)
                                    : [...f.skill_ids, skill.id],
                                }))}
                                style={{
                                  width: "100%", textAlign: "left", cursor: "pointer",
                                  fontFamily: '"VT323",monospace', fontSize: 13,
                                  padding: "5px 10px 5px 12px",
                                  background: active ? "rgba(201,162,39,0.12)" : "transparent",
                                  color: "var(--pix-ink)",
                                  border: "none",
                                  borderBottom: "1px solid var(--pix-parch-line)",
                                  display: "flex", alignItems: "center", gap: 8,
                                  transition: "background 0.1s",
                                }}
                              >
                                <span style={{
                                  width: 13, height: 13, flexShrink: 0,
                                  border: `2px solid ${active ? "var(--pix-gold)" : "var(--pix-wood-dark)"}`,
                                  background: active ? "var(--pix-gold)" : "transparent",
                                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                                  fontSize: 9, color: "var(--pix-wood-darkest)",
                                }}>
                                  {active ? "✓" : ""}
                                </span>
                                {skill.name}
                              </button>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              {/* Selected skill pills */}
              {agentForm.skill_ids.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                  {agentForm.skill_ids.map((sid) => {
                    const skill = skills.find((s) => s.id === sid);
                    if (!skill) return null;
                    return (
                      <span key={sid} style={{
                        fontFamily: '"VT323",monospace', fontSize: 12,
                        padding: "2px 6px 2px 8px",
                        background: "var(--pix-gold)", color: "var(--pix-wood-darkest)",
                        border: "2px solid var(--pix-gold-dark)",
                        display: "inline-flex", alignItems: "center", gap: 4,
                      }}>
                        {skill.name}
                        <button
                          type="button"
                          onClick={() => setAgentForm((f) => ({ ...f, skill_ids: f.skill_ids.filter((id) => id !== sid) }))}
                          style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", padding: 0, lineHeight: 1, fontSize: 14 }}
                        >
                          ×
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
              <p style={{ fontFamily: '"VT323",monospace', fontSize: 11, color: "var(--pix-ink-soft)", marginTop: 4 }}>
                Selected skills append expertise to the system prompt
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="pix-field-label">System Prompt</label>
              <div style={{ fontFamily: '"VT323",monospace', fontSize: 12, color: "var(--pix-ink-soft)", marginBottom: 4 }}>
                Template: describe role, responsibilities, and behavior. Import from .md file below.
              </div>
              {/* Import from .md file */}
              <div style={{ marginBottom: 8 }}>
                <input
                  ref={mdImportRef}
                  type="file"
                  accept=".md,.txt"
                  onChange={handleImportMd}
                  style={{ display: "none" }}
                />
                <PixelButton onClick={() => mdImportRef.current?.click()}>
                  <Upload className="h-3.5 w-3.5" /> Import from .md
                </PixelButton>
              </div>
              <Textarea
                placeholder="Describe what this agent does and how it should behave…"
                rows={5}
                value={agentForm.system_prompt}
                onChange={(e) => setAgentForm({ ...agentForm, system_prompt: e.target.value })}
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
              />
            </div>

            {/* ── Advanced Settings ─────────────────────────────── */}
            <div style={{ border: "3px solid var(--pix-wood-dark)", background: "var(--pix-parch-2)" }}>
              <button
                type="button"
                className="flex w-full items-center justify-between px-3 py-2.5"
                style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 14, color: "var(--pix-ink)", fontWeight: 600 }}
                onClick={() => setShowAdvanced((v) => !v)}
              >
                Advanced Settings
                <ChevronDown className={`h-4 w-4 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
              </button>
              {showAdvanced && (
                <div className="space-y-4 p-3" style={{ borderTop: "2px solid var(--pix-parch-line)" }}>
                  <div className="grid grid-cols-2 gap-3">
                    {/* Max Tokens */}
                    <div className="space-y-1.5">
                      <label className="pix-field-label">Max Tokens</label>
                      <Input
                        type="number"
                        min={1}
                        max={200000}
                        value={agentForm.max_tokens}
                        onChange={(e) =>
                          setAgentForm({ ...agentForm, max_tokens: Number(e.target.value) || 0 })
                        }
                        style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
                      />
                    </div>

                    {/* Context Window */}
                    <div className="space-y-1.5">
                      <label className="pix-field-label">Context Window</label>
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        value={agentForm.context_window_size}
                        onChange={(e) =>
                          setAgentForm({ ...agentForm, context_window_size: Number(e.target.value) || 0 })
                        }
                        style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
                      />
                      <p style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-ink-soft)" }}>messages to remember</p>
                    </div>
                  </div>

                  {/* Temperature */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="pix-field-label">Temperature</label>
                      <span style={{ fontFamily: '"VT323", monospace', fontSize: 16, color: "var(--pix-gold-dark)" }}>
                        {(agentForm.temperature / 100).toFixed(1)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={2}
                      step={0.1}
                      value={agentForm.temperature / 100}
                      onChange={(e) =>
                        setAgentForm({ ...agentForm, temperature: Math.round(Number(e.target.value) * 100) })
                      }
                      className="w-full"
                      style={{ accentColor: "var(--pix-gold)" }}
                    />
                  </div>

                  {/* Memory Type */}
                  <div className="space-y-1.5">
                    <label className="pix-field-label">Memory Type</label>
                    <Select
                      value={agentForm.memory_type}
                      onValueChange={(v) => setAgentForm({ ...agentForm, memory_type: v })}
                    >
                      <SelectTrigger style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {MEMORY_TYPE_OPTIONS.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
            </div>
          </div>
          <DialogFooter>
            <div className="flex gap-2 flex-wrap items-center">
              <PixelButton onClick={() => setAgentDialog({ open: false, editing: null })}>Cancel</PixelButton>
              {agentDialog.editing && agentDialogTab === "manual" && (
                <button onClick={() => {
                  saveTemplate({
                    name: agentForm.name,
                    role: agentForm.role,
                    system_prompt: agentForm.system_prompt,
                    runtime_kind: agentForm.runtime_kind,
                    tool_permissions: agentForm.tool_permissions,
                    max_tokens: agentForm.max_tokens,
                    temperature: agentForm.temperature,
                    memory_type: agentForm.memory_type,
                    tags: [agentForm.role || "general"],
                  });
                  toast.success("Saved as template");
                }} style={{ fontFamily: '"VT323",monospace', fontSize: 13, cursor: "pointer",
                  background: "transparent", border: "1px solid var(--pix-gold)", color: "var(--pix-gold)",
                  padding: "3px 10px", borderRadius: 2 }}>
                  💾 Save as Template
                </button>
              )}
              <PixelButton
                variant="gold"
                disabled={!agentForm.name.trim() || !agentForm.role.trim() || !agentForm.system_prompt.trim()}
                onClick={saveAgent}
              >
                Save
              </PixelButton>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Clone Agent Dialog ───────────────────────────────── */}
      <Dialog open={!!cloneAgent} onOpenChange={(v) => { if (!v) setCloneAgent(null); }}>
        <DialogContent className="pix-root max-w-sm" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, color: "var(--pix-ink)" }}>
              Clone agent to…
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p style={{ fontFamily: '"VT323", monospace', fontSize: 15, color: "var(--pix-ink-soft)" }}>
              Cloning: <strong style={{ color: "var(--pix-ink)" }}>{cloneAgent?.name}</strong>
            </p>
            {allProjects.length === 0 ? (
              <p style={{ fontFamily: '"VT323", monospace', fontSize: 15, color: "var(--pix-ink-soft)" }}>
                No other projects found.
              </p>
            ) : (
              <div className="space-y-1.5">
                <label className="pix-field-label">Target Project</label>
                <select
                  value={cloneTargetProjectId}
                  onChange={(e) => setCloneTargetProjectId(e.target.value)}
                  className="w-full rounded border px-2 py-1.5"
                  style={{ fontFamily: '"VT323", monospace', fontSize: 16, background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
                >
                  <option value="">— select project —</option>
                  {allProjects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <DialogFooter>
            <div className="flex gap-2">
              <PixelButton onClick={() => setCloneAgent(null)}>Cancel</PixelButton>
              <PixelButton
                variant="gold"
                disabled={!cloneTargetProjectId || cloningAgent}
                onClick={handleCloneAgent}
              >
                {cloningAgent ? "Cloning…" : "Clone"}
              </PixelButton>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Document Dialog ──────────────────────────────────── */}
      <Dialog open={docDialog.open} onOpenChange={(v) => setDocDialog({ open: v, editing: null })}>
        <DialogContent className="pix-root max-w-2xl" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 20, letterSpacing: "0.5px", color: "var(--pix-ink)" }}>
              {docDialog.editing ? "Edit Document" : "Add Document"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="pix-field-label">Title</label>
              <Input placeholder="Document title" value={docForm.title} onChange={(e) => setDocForm({ ...docForm, title: e.target.value })}
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }} />
            </div>
            <div className="space-y-1.5">
              <label className="pix-field-label">Content (Markdown)</label>
              <Textarea placeholder={"# Heading\n\nWrite markdown content here…"} rows={10} value={docForm.content}
                onChange={(e) => setDocForm({ ...docForm, content: e.target.value })}
                style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="pix-field-label">Tags (comma-separated)</label>
                <Input placeholder="e.g. finance, policy" value={docForm.tags} onChange={(e) => setDocForm({ ...docForm, tags: e.target.value })}
                  style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }} />
              </div>
              <div className="space-y-1.5">
                <label className="pix-field-label">Source URL (optional)</label>
                <Input placeholder="https://…" value={docForm.source_url} onChange={(e) => setDocForm({ ...docForm, source_url: e.target.value })}
                  style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <div className="flex gap-2">
              <PixelButton onClick={() => setDocDialog({ open: false, editing: null })}>Cancel</PixelButton>
              <PixelButton variant="gold" disabled={!docForm.title.trim() || !docForm.content.trim()} onClick={saveDoc}>Save</PixelButton>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── View Document Modal ──────────────────────────────── */}
      <Dialog open={!!viewDoc} onOpenChange={(v) => { if (!v) setViewDoc(null); }}>
        <DialogContent className="pix-root max-w-2xl" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, letterSpacing: "0.5px", color: "var(--pix-ink)" }}>
              {viewDoc?.title}
            </DialogTitle>
          </DialogHeader>
          <div style={{
            maxHeight: 380, overflowY: "auto",
            background: "var(--pix-parch-2)", border: "2px solid var(--pix-wood-dark)",
            padding: "12px 14px", fontFamily: '"VT323", monospace', fontSize: 15,
            color: "var(--pix-ink)", lineHeight: 1.6, whiteSpace: "pre-wrap",
          }}>
            {viewDoc?.content}
          </div>
          {viewDoc?.tags.length ? (
            <div className="flex gap-1 flex-wrap">
              {viewDoc.tags.map((t) => <span key={t} className="pix-tag">{t}</span>)}
            </div>
          ) : null}
          <DialogFooter>
            <PixelButton onClick={() => setViewDoc(null)}>Close</PixelButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Knowledge Catalog Dialog ────────────────────────── */}
      <Dialog open={catalogDialog} onOpenChange={setCatalogDialog}>
        <DialogContent className="pix-root max-w-2xl" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 20, color: "var(--pix-ink)" }}>
              Knowledge Catalog
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
            {/* Category filters */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button
                className={"pix-pill " + (knowledgeTemplateCategory === "all" ? "pix-gold" : "")}
                onClick={() => setKnowledgeTemplateCategory("all")}
              >All</button>
              {knowledgeCategories.map((cat) => (
                <button
                  key={cat}
                  className={"pix-pill " + (knowledgeTemplateCategory === cat ? "pix-gold" : "")}
                  onClick={() => setKnowledgeTemplateCategory(cat)}
                >{cat}</button>
              ))}
            </div>
            {/* Template cards */}
            <div className="pix-grid-cards">
              {knowledgeTemplates
                .filter((t) => knowledgeTemplateCategory === "all" || t.category === knowledgeTemplateCategory)
                .map((tmpl) => (
                  <div key={tmpl.id} style={{
                    background: "var(--pix-parch-2)", border: "3px solid var(--pix-wood-dark)",
                    padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6,
                  }}>
                    <div style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 14, color: "var(--pix-ink)" }}>
                      {tmpl.name}
                    </div>
                    <div style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-ink-soft)", lineHeight: 1.2 }}>
                      {tmpl.description}
                    </div>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {tmpl.tags.map((tag) => <span key={tag} className="pix-tag">{tag}</span>)}
                    </div>
                    <div style={{ marginTop: "auto", paddingTop: 4 }}>
                      <PixelButton
                        variant="gold"
                        disabled={importingTemplateId === tmpl.id}
                        onClick={async () => {
                          setImportingTemplateId(tmpl.id);
                          try {
                            const detail = await apiClient.get<{ content: string; name: string; tags: string[] }>(`/knowledge-templates/${tmpl.id}`);
                            await apiClient.post(`/projects/${id}/knowledge`, {
                              title: detail.name,
                              content: detail.content,
                              tags: detail.tags,
                              source_url: `template:${tmpl.source_key}`,
                            });
                            queryClient.invalidateQueries({ queryKey: ["knowledge", id, search] });
                            toast.success(`Imported "${detail.name}"`);
                          } catch {
                            toast.error("Failed to import template");
                          } finally {
                            setImportingTemplateId(null);
                          }
                        }}
                      >
                        {importingTemplateId === tmpl.id ? "Importing…" : "Import"}
                      </PixelButton>
                    </div>
                  </div>
                ))}
            </div>
          </div>
          <DialogFooter>
            <PixelButton onClick={() => setCatalogDialog(false)}>Close</PixelButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Obsidian Vault Sync Dialog ───────────────────────── */}
      <Dialog open={vaultDialog} onOpenChange={setVaultDialog}>
        <DialogContent className="max-w-md" style={{ background: "var(--pix-parch)", borderColor: "var(--pix-wood-dark)", borderWidth: 3 }}>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 20, letterSpacing: "0.5px", color: "var(--pix-ink)" }}>📁 Obsidian Vault — {project?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)", lineHeight: 1.4 }}>
              This project has its own Obsidian vault folder. All <code style={{ background: "var(--pix-parch-3)", padding: "0 4px" }}>.md</code> files inside are synced to the knowledge base.
            </p>
            <PixelFrame tight>
              <div className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>Vault Path</div>
              <div style={{ fontFamily: '"VT323", monospace', fontSize: 14, color: "var(--pix-ink)", wordBreak: "break-all" }}>
                {vaultPath || "Not set"}
              </div>
            </PixelFrame>
            {/* Folder structure preview */}
            <PixelFrame variant="screen" tight>
              <div className="pix-mono" style={{ fontSize: 12, color: "#9bdbaa", lineHeight: 1.5 }}>
                <div style={{ marginBottom: 4, opacity: 0.7 }}>📁 Folder structure inside vault:</div>
                <pre style={{ margin: 0, fontSize: 12 }}>
{`${vaultPath || "~/Documents/ObsidianVault/<project>"}/
├── 00_index.md
│   (auto-generated project index)
│
├── pm/
│   (Product Manager notes, requirements, PRDs)
├── ba/
│   (Business Analyst docs, user stories)
├── sa/
│   (Solution Architect diagrams, decisions)
├── dev/
│   (Developer docs, API specs, runbooks)
├── qa/
│   (QA test plans, bug reports)
│
├── handoffs/
│   (Agent handoff transcripts, state files)
├── decisions/
│   (Architecture Decision Records — ADRs)
├── risks/
│   (Risk registers, mitigation plans)
└── final/
    (Deliverables, exports, signed-off docs)`}
                </pre>
              </div>
            </PixelFrame>
          </div>
          <DialogFooter>
            <div className="pix-root flex gap-2">
              <PixelButton onClick={() => setVaultDialog(false)}>Close</PixelButton>
              <PixelButton variant="gold" disabled={!vaultPath.trim() || syncing} onClick={() => handleVaultSync()}>
                {syncing ? "Syncing…" : "Sync Now"}
              </PixelButton>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── New Workflow Dialog ───────────────────────────────── */}
      {newWorkflowDialog.open && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100,
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "var(--pix-parch)", border: "3px solid var(--pix-wood-dark)",
            boxShadow: "inset 0 0 0 3px var(--pix-frame-light), inset 0 0 0 6px var(--pix-wood)",
            borderRadius: 4, padding: 24, maxWidth: 400, width: "90%",
            fontFamily: '"Pixelify Sans", sans-serif' }}>
            <h3 style={{ color: "var(--pix-ink)", marginBottom: 16, fontSize: 18, letterSpacing: 0.5 }}>
              + New Workflow
            </h3>
            <div className="space-y-1.5" style={{ marginBottom: 16 }}>
              <label className="pix-field-label">Workflow Name</label>
              <Input
                autoFocus
                placeholder="e.g. Daily Analysis"
                value={newWorkflowDialog.name}
                onChange={(e) => setNewWorkflowDialog(d => ({ ...d, name: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newWorkflowDialog.name.trim()) {
                    createWorkflow.mutate(newWorkflowDialog.name.trim());
                    setNewWorkflowDialog({ open: false, name: "" });
                  }
                  if (e.key === "Escape") setNewWorkflowDialog({ open: false, name: "" });
                }}
                style={{ fontFamily: '"VT323",monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
              />
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <PixelButton onClick={() => setNewWorkflowDialog({ open: false, name: "" })}>
                Cancel
              </PixelButton>
              <PixelButton variant="gold"
                disabled={!newWorkflowDialog.name.trim() || createWorkflow.isPending}
                onClick={() => {
                  if (newWorkflowDialog.name.trim()) {
                    createWorkflow.mutate(newWorkflowDialog.name.trim());
                    setNewWorkflowDialog({ open: false, name: "" });
                  }
                }}>
                {createWorkflow.isPending ? "Creating…" : "Create →"}
              </PixelButton>
            </div>
          </div>
        </div>
      )}

      {/* ── Workflow Template Modal ──────────────────────────── */}
      {showTemplateModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100,
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "var(--pix-parch)", border: "3px solid var(--pix-wood-dark)",
            borderRadius: 4, padding: 24, maxWidth: 480, width: "90%",
            fontFamily: '"Pixelify Sans", sans-serif' }}>
            <h3 style={{ color: "var(--pix-ink)", marginBottom: 16, fontSize: 18 }}>📋 Workflow Templates</h3>

            {/* Template card */}
            <div style={{ border: "2px solid var(--pix-wood-dark)", borderRadius: 3, padding: 16,
              background: "var(--pix-parch-2)", marginBottom: 16, cursor: creatingTemplate ? "not-allowed" : "pointer",
              opacity: creatingTemplate ? 0.6 : 1 }}
              onClick={() => { if (!creatingTemplate) handleCreateFromTemplate("crypto_trading"); }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: "var(--pix-ink)" }}>🪙 Crypto Trading Flow</div>
              <div style={{ fontSize: 12, fontFamily: '"VT323",monospace', marginTop: 4, color: "var(--pix-ink)" }}>
                Market Data → Analyst → Signal → Risk → Approval → Execute → Monitor → Summary
              </div>
              <div style={{ fontSize: 11, marginTop: 6, color: "var(--pix-gold)" }}>
                8 steps · schedule trigger · cron every 2h
              </div>
            </div>

            <button onClick={() => setShowTemplateModal(false)} disabled={creatingTemplate}
              style={{ background: "var(--pix-wood-dark)", color: "var(--pix-parch)", border: "none",
                padding: "8px 20px", cursor: creatingTemplate ? "not-allowed" : "pointer",
                fontFamily: '"Pixelify Sans",sans-serif', borderRadius: 2, opacity: creatingTemplate ? 0.6 : 1 }}>
              {creatingTemplate ? "Creating…" : "Cancel"}
            </button>
          </div>
        </div>
      )}

      {/* ── Workflow Settings Dialog ─────────────────────────── */}
      {(() => {
        const wf = workflowSettings.workflow;
        if (!workflowSettings.open || !wf) return null;
        return (
          <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100,
            display: "flex", alignItems: "center", justifyContent: "center" }}>
            <div style={{ background: "var(--pix-parch)", border: "3px solid var(--pix-wood-dark)",
              borderRadius: 4, padding: 24, maxWidth: 480, width: "90%",
              fontFamily: '"Pixelify Sans", sans-serif' }}>
              <h3 style={{ color: "var(--pix-ink)", marginBottom: 16, fontSize: 18 }}>
                ⚙️ Workflow Settings — {wf.name}
              </h3>
              <div className="space-y-3" style={{ marginBottom: 16 }}>
                <div className="space-y-1.5">
                  <label className="pix-field-label">Name</label>
                  <Input
                    value={wf.name}
                    onChange={(e) => setWorkflowSettings({ open: true, workflow: { ...wf, name: e.target.value } })}
                    style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="pix-field-label">Description</label>
                  <Textarea
                    value={wf.description || ""}
                    onChange={(e) => setWorkflowSettings({ open: true, workflow: { ...wf, description: e.target.value } })}
                    rows={2}
                    style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="pix-field-label">Trigger</label>
                  <div style={{ display: "flex", gap: 6 }}>
                    {(["manual", "schedule", "event"] as const).map(kind => (
                      <button
                        key={kind}
                        onClick={() => setWorkflowSettings({ open: true, workflow: { ...wf, trigger_kind: kind } })}
                        style={{
                          fontFamily: '"VT323", monospace', fontSize: 13, cursor: "pointer",
                          padding: "4px 12px", borderRadius: 2,
                          background: wf.trigger_kind === kind ? "var(--pix-wood-dark)" : "var(--pix-parch-2)",
                          color: wf.trigger_kind === kind ? "var(--pix-parch)" : "var(--pix-ink)",
                          border: `2px solid ${wf.trigger_kind === kind ? "var(--pix-wood-darkest)" : "var(--pix-wood-dark)"}`,
                        }}
                      >
                        {kind === "manual" ? "▶ Manual" : kind === "schedule" ? "⏰ Schedule" : "⚡ Webhook"}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="pix-field-label">Status</label>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      onClick={() => setWorkflowSettings({ open: true, workflow: { ...wf, is_enabled: true } })}
                      style={{
                        fontFamily: '"VT323", monospace', fontSize: 13, cursor: "pointer",
                        padding: "4px 12px", borderRadius: 2,
                        background: wf.is_enabled ? "var(--pix-gold)" : "var(--pix-parch-2)",
                        color: wf.is_enabled ? "var(--pix-wood-darkest)" : "var(--pix-ink)",
                        border: `2px solid ${wf.is_enabled ? "var(--pix-gold)" : "var(--pix-wood-dark)"}`,
                      }}
                    >
                      Enabled
                    </button>
                    <button
                      onClick={() => setWorkflowSettings({ open: true, workflow: { ...wf, is_enabled: false } })}
                      style={{
                        fontFamily: '"VT323", monospace', fontSize: 13, cursor: "pointer",
                        padding: "4px 12px", borderRadius: 2,
                        background: !wf.is_enabled ? "#a04040" : "var(--pix-parch-2)",
                        color: !wf.is_enabled ? "#fff" : "var(--pix-ink)",
                        border: `2px solid ${!wf.is_enabled ? "#a04040" : "var(--pix-wood-dark)"}`,
                      }}
                    >
                      Disabled
                    </button>
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <PixelButton onClick={() => setWorkflowSettings({ open: false, workflow: null })}>
                  Cancel
                </PixelButton>
                <PixelButton
                  variant="gold"
                  disabled={updateWorkflowMeta.isPending}
                  onClick={() => {
                    updateWorkflowMeta.mutate({
                      wfId: wf.id,
                      body: {
                        name: wf.name,
                        description: wf.description,
                        trigger_kind: wf.trigger_kind,
                        is_enabled: wf.is_enabled,
                      },
                    });
                    setWorkflowSettings({ open: false, workflow: null });
                  }}
                >
                  {updateWorkflowMeta.isPending ? "Saving…" : "Save"}
                </PixelButton>
              </div>
            </div>
          </div>
        );
      })()}

      </ErrorBoundary>
    </div>
  );
}
