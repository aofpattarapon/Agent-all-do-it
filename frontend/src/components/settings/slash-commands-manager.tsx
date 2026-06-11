"use client";

import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Textarea,
} from "@/components/ui";
import { ApiError } from "@/lib/api-client";
import { BUILTIN_COMMAND_LIST, isBuiltinEnabled, useSlashCommands } from "@/hooks";
import type { UserSlashCommandRecord } from "@/lib/slash-commands-api";

const NAME_PATTERN = /^[a-z0-9][a-z0-9-]{0,31}$/;

function PixToggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className={"pix-toggle " + (checked ? "pix-on" : "")}
      style={disabled ? { opacity: 0.5, cursor: "not-allowed" } : undefined}
    >
      <span aria-hidden className="pix-knob" />
    </button>
  );
}

export function SlashCommandsManager() {
  const {
    records,
    isLoading,
    error,
    refresh,
    createCustom,
    updateCustom,
    setBuiltinEnabled,
    remove,
  } = useSlashCommands();

  const customs = records.filter((r) => r.prompt !== null);

  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftPrompt, setDraftPrompt] = useState("");
  const [draftEnabled, setDraftEnabled] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const openCreate = () => {
    setEditingId("new");
    setDraftName("");
    setDraftPrompt("");
    setDraftEnabled(true);
  };

  const openEdit = (record: UserSlashCommandRecord) => {
    setEditingId(record.id);
    setDraftName(record.name);
    setDraftPrompt(record.prompt ?? "");
    setDraftEnabled(record.is_enabled);
  };

  const closeDialog = () => {
    if (submitting) return;
    setEditingId(null);
  };

  const handleSubmit = async () => {
    const name = draftName.trim().toLowerCase();
    const prompt = draftPrompt.trim();
    if (!NAME_PATTERN.test(name)) {
      toast.error("Name must be lowercase letters, digits, and hyphens (max 32 chars).");
      return;
    }
    if (!prompt) {
      toast.error("Prompt cannot be empty.");
      return;
    }
    setSubmitting(true);
    try {
      if (editingId === "new") {
        await createCustom({ name, prompt });
        toast.success(`/${name} created.`);
      } else if (editingId) {
        await updateCustom(editingId, { name, prompt, is_enabled: draftEnabled });
        toast.success(`/${name} updated.`);
      }
      setEditingId(null);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "Failed to save command";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleCustom = async (record: UserSlashCommandRecord, next: boolean) => {
    try {
      await updateCustom(record.id, { is_enabled: next });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to toggle");
    }
  };

  const handleToggleBuiltin = async (name: string, next: boolean) => {
    try {
      await setBuiltinEnabled(name, next);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to toggle");
    }
  };

  const handleDelete = async (record: UserSlashCommandRecord) => {
    if (!confirm(`Delete /${record.name}?`)) return;
    try {
      await remove(record.id);
      toast.success(`/${record.name} deleted.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete");
    }
  };

  return (
    <div className="space-y-8">
      {error && (
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{
            border: "2px solid var(--pix-red)",
            background: "#f4dedb",
            color: "var(--pix-red)",
            fontFamily: '"VT323", monospace',
            fontSize: "14px",
          }}
        >
          <span>{error}</span>
          <button type="button" className="pix-btn" onClick={() => refresh()}>
            Retry
          </button>
        </div>
      )}

      {/* Built-in commands */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <h3
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                fontSize: "15px",
                fontWeight: 700,
                color: "var(--pix-ink)",
              }}
            >
              Built-in commands
            </h3>
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "13px",
                color: "var(--pix-ink-soft)",
                marginTop: "2px",
              }}
            >
              Disable any you don&apos;t want to see in the palette.
            </p>
          </div>
        </div>
        <div className="pix-frame" style={{ padding: 0, overflow: "hidden" }}>
          <ul style={{ display: "flex", flexDirection: "column" }}>
            {BUILTIN_COMMAND_LIST.map((cmd, idx) => {
              const enabled = isBuiltinEnabled(cmd.name, records);
              return (
                <li
                  key={cmd.name}
                  className="flex items-center gap-4 px-4 py-3"
                  style={{
                    borderBottom:
                      idx < BUILTIN_COMMAND_LIST.length - 1
                        ? "2px solid var(--pix-parch-line)"
                        : "none",
                  }}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <code
                        style={{
                          fontFamily: '"VT323", monospace',
                          fontSize: "13px",
                          background: "var(--pix-parch-3)",
                          padding: "1px 6px",
                          border: "1px solid var(--pix-wood-dark)",
                          color: "var(--pix-ink)",
                        }}
                      >
                        /{cmd.name}
                      </code>
                      {cmd.action.kind === "client" && (
                        <span
                          style={{
                            fontFamily: '"VT323", monospace',
                            fontSize: "11px",
                            letterSpacing: "0.05em",
                            textTransform: "uppercase",
                            color: "var(--pix-ink-soft)",
                          }}
                        >
                          local
                        </span>
                      )}
                    </div>
                    <p
                      style={{
                        fontFamily: '"VT323", monospace',
                        fontSize: "13px",
                        color: "var(--pix-ink-soft)",
                        marginTop: "4px",
                      }}
                    >
                      {cmd.description}
                    </p>
                  </div>
                  <PixToggle
                    checked={enabled}
                    onChange={(v) => handleToggleBuiltin(cmd.name, v)}
                    disabled={isLoading}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      {/* Custom commands */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <h3
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                fontSize: "15px",
                fontWeight: 700,
                color: "var(--pix-ink)",
              }}
            >
              Your custom commands
            </h3>
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "13px",
                color: "var(--pix-ink-soft)",
                marginTop: "2px",
              }}
            >
              Slash shortcuts for prompts you type often. Typing <code>/name</code> in chat sends
              the stored prompt.
            </p>
          </div>
          <button type="button" className="pix-btn pix-green" onClick={openCreate}>
            <Plus size={14} />
            New
          </button>
        </div>

        {customs.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center text-center"
            style={{
              border: "3px dashed var(--pix-parch-line)",
              background: "var(--pix-parch-2)",
              padding: "48px 24px",
            }}
          >
            <p
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                fontSize: "16px",
                fontWeight: 600,
                color: "var(--pix-ink-soft)",
              }}
            >
              No custom commands yet
            </p>
            <p
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: "14px",
                color: "var(--pix-ink-soft)",
                marginTop: "8px",
              }}
            >
              Create one to send a long prompt with a few keystrokes.
            </p>
          </div>
        ) : (
          <div className="pix-frame" style={{ padding: 0, overflow: "hidden" }}>
            <ul style={{ display: "flex", flexDirection: "column" }}>
              {customs.map((record, idx) => (
                <li
                  key={record.id}
                  className="flex items-start gap-4 px-4 py-3"
                  style={{
                    borderBottom:
                      idx < customs.length - 1 ? "2px solid var(--pix-parch-line)" : "none",
                  }}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <code
                        style={{
                          fontFamily: '"VT323", monospace',
                          fontSize: "13px",
                          background: "var(--pix-parch-3)",
                          padding: "1px 6px",
                          border: "1px solid var(--pix-wood-dark)",
                          color: "var(--pix-ink)",
                        }}
                      >
                        /{record.name}
                      </code>
                    </div>
                    <p
                      style={{
                        fontFamily: '"VT323", monospace',
                        fontSize: "13px",
                        color: "var(--pix-ink-soft)",
                        marginTop: "4px",
                        lineHeight: 1.3,
                      }}
                    >
                      {record.prompt}
                    </p>
                  </div>
                  <PixToggle
                    checked={record.is_enabled}
                    onChange={(v) => handleToggleCustom(record, v)}
                  />
                  <button
                    type="button"
                    onClick={() => openEdit(record)}
                    className="pix-iconbtn"
                    title="Edit"
                    aria-label="Edit"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(record)}
                    className="pix-iconbtn pix-danger"
                    title="Delete"
                    aria-label="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <Dialog open={editingId !== null} onOpenChange={(o) => !o && closeDialog()}>
        <DialogContent className="pix-root" style={{ background: "var(--pix-parch)", border: "3px solid var(--pix-wood-dark)", maxWidth: "480px" }}>
          <DialogHeader>
            <DialogTitle
              style={{
                fontFamily: '"Pixelify Sans", sans-serif',
                fontSize: "18px",
                color: "var(--pix-gold-dark)",
              }}
            >
              {editingId === "new" ? "New custom command" : `Edit /${draftName}`}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label
                htmlFor="cmd-name"
                style={{
                  fontFamily: '"Pixelify Sans", sans-serif',
                  fontSize: "14px",
                  color: "var(--pix-ink)",
                }}
              >
                Name
              </Label>
              <div className="mt-1.5 flex items-center gap-2">
                <span
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "16px",
                    color: "var(--pix-ink-soft)",
                  }}
                >
                  /
                </span>
                <Input
                  id="cmd-name"
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value.toLowerCase())}
                  placeholder="todo"
                  maxLength={32}
                  autoFocus
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: "15px",
                    background: "var(--pix-parch-2)",
                    border: "2px solid var(--pix-wood-dark)",
                    boxShadow: "inset 0 0 0 2px var(--pix-parch)",
                  }}
                />
              </div>
              <p
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "12px",
                  color: "var(--pix-ink-soft)",
                  marginTop: "4px",
                }}
              >
                Lowercase letters, digits, hyphens. Max 32 chars.
              </p>
            </div>
            <div>
              <Label
                htmlFor="cmd-prompt"
                style={{
                  fontFamily: '"Pixelify Sans", sans-serif',
                  fontSize: "14px",
                  color: "var(--pix-ink)",
                }}
              >
                Prompt
              </Label>
              <Textarea
                id="cmd-prompt"
                value={draftPrompt}
                onChange={(e) => setDraftPrompt(e.target.value)}
                placeholder="Summarize the conversation as a checklist of action items."
                rows={6}
                maxLength={10_000}
                className="mt-1.5 font-mono text-sm"
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "14px",
                  background: "var(--pix-parch-2)",
                  border: "2px solid var(--pix-wood-dark)",
                  boxShadow: "inset 0 0 0 2px var(--pix-parch)",
                }}
              />
              <p
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: "12px",
                  color: "var(--pix-ink-soft)",
                  marginTop: "4px",
                }}
              >
                Sent as a regular user message when you type <code>/{draftName || "name"}</code>.
              </p>
            </div>
            {editingId !== "new" && (
              <div className="flex items-center gap-3">
                <PixToggle checked={draftEnabled} onChange={setDraftEnabled} />
                <Label
                  htmlFor="cmd-enabled"
                  className="text-sm font-normal"
                  style={{
                    fontFamily: '"Pixelify Sans", sans-serif',
                    fontSize: "14px",
                    color: "var(--pix-ink)",
                  }}
                >
                  Enabled
                </Label>
              </div>
            )}
          </div>
          <DialogFooter className="gap-2">
            <button
              type="button"
              className="pix-btn"
              onClick={closeDialog}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="button"
              className="pix-btn pix-green"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? "Saving…" : editingId === "new" ? "Create" : "Save"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
