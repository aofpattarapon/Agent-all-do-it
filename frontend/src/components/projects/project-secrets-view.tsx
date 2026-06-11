"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { PixelButton, PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { ProjectSectionShell } from "@/components/projects/ProjectSectionShell";

interface Secret {
  id: string;
  name: string;
  provider: string;
  environment: string;
  value_masked: string;
  status: string;
  last_used_at: string | null;
}

export default function ProjectSecretsView({
  projectId,
  embedded = false,
}: {
  projectId: string;
  embedded?: boolean;
}) {
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", provider: "openai", environment: "all", value: "" });

  useEffect(() => {
    fetchSecrets();
  }, [projectId]);

  async function fetchSecrets() {
    try {
      const data = await apiClient.get<{ items: Secret[]; total: number }>(`/projects/${projectId}/secrets`);
      setSecrets(data.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  async function createSecret() {
    try {
      await apiClient.post(`/projects/${projectId}/secrets`, form);
      setShowForm(false);
      setForm({ name: "", provider: "openai", environment: "all", value: "" });
      fetchSecrets();
    } catch {
      alert("Failed to create secret");
    }
  }

  async function testSecret(secretId: string) {
    try {
      const res = await apiClient.post<{ success: boolean; message: string }>(`/projects/${projectId}/secrets/${secretId}/test`);
      alert(res.message);
    } catch {
      alert("Test failed");
    }
  }

  async function deleteSecret(secretId: string) {
    if (!confirm("Delete this secret?")) return;
    try {
      await apiClient.delete(`/projects/${projectId}/secrets/${secretId}`);
      fetchSecrets();
    } catch {
      alert("Failed to delete");
    }
  }

  const content = (
    <>
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Secrets</div>
            <h2>API Keys & Credentials</h2>
          </div>
          <PixelButton variant="gold" onClick={() => setShowForm(!showForm)}>
            {showForm ? "Cancel" : "+ Add Secret"}
          </PixelButton>
        </div>
      </PixelFrame>

      {showForm && (
        <PixelFrame>
          <SectionLabel>New Secret</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 480 }}>
            <input
              className="pix-input"
              placeholder="Name (e.g. OpenAI Production)"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <select
              className="pix-input"
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value })}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="google">Google</option>
              <option value="openrouter">OpenRouter</option>
              <option value="discord">Discord</option>
              <option value="github">GitHub</option>
              <option value="openclaw">OpenClaw</option>
              <option value="generic">Generic</option>
            </select>
            <input
              className="pix-input"
              placeholder="Environment (all, dev, staging, prod)"
              value={form.environment}
              onChange={(e) => setForm({ ...form, environment: e.target.value })}
            />
            <input
              className="pix-input"
              type="password"
              placeholder="Secret value"
              value={form.value}
              onChange={(e) => setForm({ ...form, value: e.target.value })}
            />
            <PixelButton variant="green" onClick={createSecret}>Save Secret</PixelButton>
          </div>
        </PixelFrame>
      )}

      {loading ? (
        <PixelFrame variant="screen">
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>Loading secrets…</div>
        </PixelFrame>
      ) : secrets.length === 0 ? (
        <PixelFrame variant="screen">
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>
            No secrets stored yet. Add your first API key above.
          </div>
        </PixelFrame>
      ) : (
        <div className="pix-grid-cards">
          {secrets.map((s) => (
            <PixelFrame key={s.id} variant="parchment" tight>
              <div className="pix-pcard-head">
                <span className="pix-pname">🔑 {s.name}</span>
                <span className={s.status === "active" ? "pix-pill pix-completed" : "pix-pill pix-failed"}>
                  {s.status}
                </span>
              </div>
              <div className="pix-mono" style={{ fontSize: 13, marginTop: 4 }}>
                Provider: {s.provider} · Env: {s.environment}
              </div>
              <div className="pix-mono" style={{ fontSize: 13, marginTop: 4, color: "var(--pix-muted)" }}>
                Value: {s.value_masked}
              </div>
              <div className="pix-pcard-actions" style={{ marginTop: 8 }}>
                <PixelButton onClick={() => testSecret(s.id)}>Test</PixelButton>
                <PixelButton variant="default" onClick={() => deleteSecret(s.id)}>Delete</PixelButton>
              </div>
            </PixelFrame>
          ))}
        </div>
      )}
    </>
  );

  if (embedded) return <div className="space-y-4">{content}</div>;

  return <ProjectSectionShell projectId={projectId} activeSection="secrets">{content}</ProjectSectionShell>;
}
