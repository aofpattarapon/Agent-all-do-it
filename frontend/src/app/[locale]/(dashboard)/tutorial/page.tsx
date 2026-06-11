"use client";

import { useRouter } from "next/navigation";
import { PixelFrame, PixelButton, SectionLabel } from "@/components/pixel-ui";
import { BookOpen, Bot, FolderKanban, Sparkles, Settings, Play, Lightbulb } from "lucide-react";

const STEPS = [
  {
    icon: <FolderKanban className="h-6 w-6" />,
    title: "1. Create a Project",
    desc: "Projects are workspaces where you organize agents, knowledge, and workflows. Click '+ New Project' on the Projects page to get started.",
  },
  {
    icon: <Bot className="h-6 w-6" />,
    title: "2. Add Agents",
    desc: "Agents are AI workers that perform tasks. You can create them manually or pick from 46+ templates. Choose a character, runtime (Claude, OpenAI, Ollama), and skills.",
  },
  {
    icon: <Sparkles className="h-6 w-6" />,
    title: "3. Pick Skills & Models",
    desc: "Attach skills from the catalog (React, DevOps, Security, etc.) and select the AI model that fits your task — Sonnet, Opus, GPT-5.4, and more.",
  },
  {
    icon: <BookOpen className="h-6 w-6" />,
    title: "4. Add Knowledge",
    desc: "Upload documents, sync Obsidian vaults, or import from the Knowledge Catalog. Agents use this context to give better answers.",
  },
  {
    icon: <Play className="h-6 w-6" />,
    title: "5. Run Workflows",
    desc: "Create automated workflows that chain agents together. Schedule them or trigger manually from the Runs tab.",
  },
  {
    icon: <Settings className="h-6 w-6" />,
    title: "6. Configure Settings",
    desc: "Manage your profile, account, appearance, and console preferences from the Settings sidebar menu.",
  },
];

const TIPS = [
  "Use the Office tab to watch agents work in a pixel-art room.",
  "The History page shows all runs across projects with filters.",
  "Templates save time — start from a template and customize.",
  "Skills inject domain expertise into agent system prompts.",
  "Knowledge documents are searchable and taggable for quick access.",
];

export default function TutorialPage() {
  const router = useRouter();

  return (
    <div className="pix-root mx-auto w-full max-w-5xl space-y-6">
      <div className="pix-greet">
        <div>
          <div className="pix-eyebrow">Getting Started</div>
          <h2>📖 Tutorial</h2>
        </div>
        <PixelButton variant="gold" onClick={() => router.push("/projects")}>
          Go to Projects →
        </PixelButton>
      </div>

      <PixelFrame>
        <SectionLabel>Quick Start Guide</SectionLabel>
        <div className="space-y-4">
          {STEPS.map((step, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                gap: 14,
                alignItems: "flex-start",
                background: "var(--pix-parch-2)",
                border: "3px solid var(--pix-wood-dark)",
                padding: "14px 16px",
              }}
            >
              <div style={{ color: "var(--pix-gold-dark)", marginTop: 2 }}>{step.icon}</div>
              <div>
                <div style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 17, color: "var(--pix-ink)" }}>
                  {step.title}
                </div>
                <div style={{ fontFamily: '"VT323", monospace', fontSize: 15, color: "var(--pix-ink-soft)", lineHeight: 1.3, marginTop: 4 }}>
                  {step.desc}
                </div>
              </div>
            </div>
          ))}
        </div>
      </PixelFrame>

      <PixelFrame>
        <SectionLabel>Pro Tips</SectionLabel>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
          {TIPS.map((tip, i) => (
            <div
              key={i}
              style={{
                background: "var(--pix-parch-2)",
                border: "3px solid var(--pix-wood-dark)",
                padding: "12px 14px",
                display: "flex",
                gap: 10,
                alignItems: "flex-start",
              }}
            >
              <Lightbulb className="h-5 w-5 shrink-0" style={{ color: "var(--pix-gold-dark)" }} />
              <span style={{ fontFamily: '"VT323", monospace', fontSize: 15, color: "var(--pix-ink)", lineHeight: 1.3 }}>
                {tip}
              </span>
            </div>
          ))}
        </div>
      </PixelFrame>
    </div>
  );
}
