"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { PixelButton, PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { ProjectSectionShell } from "@/components/projects/ProjectSectionShell";

interface Integration {
  id: string;
  name: string;
  kind: string;
  config_json: Record<string, unknown>;
  status: string;
  last_check_at: string | null;
  error_text: string;
}

export default function ProjectIntegrationsView({
  projectId,
  embedded = false,
}: {
  projectId: string;
  embedded?: boolean;
}) {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", kind: "openclaw", config_json: "{}" });

  useEffect(() => {
    fetchIntegrations();
  }, [projectId]);

  async function fetchIntegrations() {
    try {
      const data = await apiClient.get<{ items: Integration[]; total: number }>(`/projects/${projectId}/integrations`);
      setIntegrations(data.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  async function createIntegration() {
    try {
      const config = JSON.parse(form.config_json);
      await apiClient.post(`/projects/${projectId}/integrations`, { name: form.name, kind: form.kind, config_json: config });
      setShowForm(false);
      setForm({ name: "", kind: "openclaw", config_json: "{}" });
      fetchIntegrations();
    } catch {
      alert("Failed to create integration. Check JSON config.");
    }
  }

  async function testIntegration(integrationId: string) {
    try {
      const res = await apiClient.post<{ success: boolean; message: string }>(`/projects/${projectId}/integrations/${integrationId}/test`);
      alert(res.message);
      fetchIntegrations();
    } catch {
      alert("Test failed");
    }
  }

  async function deleteIntegration(integrationId: string) {
    if (!confirm("Delete this integration?")) return;
    try {
      await apiClient.delete(`/projects/${projectId}/integrations/${integrationId}`);
      fetchIntegrations();
    } catch {
      alert("Failed to delete");
    }
  }

  const statusDot = (status: string) => {
    if (status === "connected") return "🟢";
    if (status === "error") return "🔴";
    if (status === "pending") return "🟡";
    return "⚪";
  };

  const content = (
    <>
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="pix-eyebrow">Integrations</div>
            <h2>External Services</h2>
          </div>
          <PixelButton variant="gold" onClick={() => setShowForm(!showForm)}>
            {showForm ? "Cancel" : "+ Add Integration"}
          </PixelButton>
        </div>
      </PixelFrame>

      {showForm && (
        <PixelFrame>
          <SectionLabel>New Integration</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 480 }}>
            <input
              className="pix-input"
              placeholder="Name (e.g. OpenClaw Gateway)"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <select
              className="pix-input"
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              <option value="openclaw">OpenClaw</option>
              <option value="discord">Discord</option>
              <option value="slack">Slack</option>
              <option value="github">GitHub</option>
              <option value="obsidian">Obsidian</option>
              <option value="telegram">Telegram</option>
              <option value="jira">Jira</option>
            </select>
            <textarea
              className="pix-input"
              rows={4}
              placeholder='Config JSON e.g. {"gateway_url":"http://localhost:9000"}'
              value={form.config_json}
              onChange={(e) => setForm({ ...form, config_json: e.target.value })}
            />
            <PixelButton variant="green" onClick={createIntegration}>Save Integration</PixelButton>
          </div>
        </PixelFrame>
      )}

      {loading ? (
        <PixelFrame variant="screen">
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>Loading integrations…</div>
        </PixelFrame>
      ) : integrations.length === 0 ? (
        <PixelFrame variant="screen">
          <div className="pix-empty" style={{ color: "#9bdbaa" }}>
            No integrations yet. Connect OpenClaw, Discord, Obsidian, and more.
          </div>
        </PixelFrame>
      ) : (
        <div className="pix-grid-cards">
          {integrations.map((i) => (
            <PixelFrame key={i.id} variant="parchment" tight>
              <div className="pix-pcard-head">
                <span className="pix-pname">
                  {statusDot(i.status)} {i.name}
                </span>
                <span className="pix-pill">{i.kind}</span>
              </div>
              <div className="pix-mono" style={{ fontSize: 13, marginTop: 4, color: "var(--pix-muted)" }}>
                Status: {i.status}
                {i.last_check_at && ` · Checked ${new Date(i.last_check_at).toLocaleString()}`}
              </div>
              {i.error_text && (
                <div className="pix-mono" style={{ fontSize: 12, marginTop: 4, color: "#df5b53" }}>
                  Error: {i.error_text}
                </div>
              )}
              <div className="pix-pcard-actions" style={{ marginTop: 8 }}>
                <PixelButton onClick={() => testIntegration(i.id)}>Test</PixelButton>
                <PixelButton variant="default" onClick={() => deleteIntegration(i.id)}>Delete</PixelButton>
              </div>
            </PixelFrame>
          ))}
        </div>
      )}
    </>
  );

  if (embedded) return <div className="space-y-4">{content}</div>;

  return <ProjectSectionShell projectId={projectId} activeSection="integrations">{content}</ProjectSectionShell>;
}
