"use client";

// Learning read-only dashboard (Phase F).
//
// Displays trade lessons stored as KnowledgeDocument entries with source_type="trade_lesson".
// No lesson injection, no editing, no deletion, no creation. Pure visibility.

import { useQuery } from "@tanstack/react-query";
import { BookOpen, BookOpenText, Calendar, GraduationCap, Tag } from "lucide-react";
import type { ReactNode } from "react";

import { PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { apiClient } from "@/lib/api-client";

export interface LearningLesson {
  id: string;
  title: string;
  content: string;
  tags: string[];
  source_type: string;
  source_url: string | null;
  created_at: string;
}

export interface LearningLessonList {
  items: LearningLesson[];
  total: number;
}

interface UseLessonsResult {
  data: LearningLessonList | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function useLearningLessons(projectId: string): UseLessonsResult {
  return useQuery<LearningLessonList>({
    queryKey: ["learning-lessons", projectId],
    queryFn: () => apiClient.get<LearningLessonList>(`/projects/${projectId}/learning/lessons`),
  });
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function extractSymbol(tags: string[]): string | null {
  return tags.find((t) => t && t !== "trade_lesson" && t !== "win" && t !== "loss") ?? null;
}

function extractOutcome(tags: string[]): string | null {
  if (tags.includes("loss")) return "loss";
  if (tags.includes("win")) return "win";
  return null;
}

function extractTradeId(content: string): string | null {
  const m = content.match(/\*\*Trade ID\*\*:\s*([a-f0-9-]{8,})/i);
  return m?.[1] ?? null;
}

function LessonCard({ lesson }: { lesson: LearningLesson }) {
  const symbol = extractSymbol(lesson.tags);
  const outcome = extractOutcome(lesson.tags);
  const tradeId = extractTradeId(lesson.content);

  return (
    <PixelFrame tight data-testid="learning-lesson-card">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <BookOpenText className="h-4 w-4" style={{ color: "var(--pix-gold)" }} />
          <span className="pix-row-title" data-testid="lesson-title">{lesson.title}</span>
          {symbol && (
            <span className="pix-pill pix-gold" data-testid="lesson-symbol">
              {symbol}
            </span>
          )}
          {outcome && (
            <span
              className="pix-pill"
              style={{
                color: outcome === "loss" ? "var(--pix-danger)" : "var(--pix-success)",
                borderColor: outcome === "loss" ? "var(--pix-danger)" : "var(--pix-success)",
              }}
              data-testid="lesson-outcome"
            >
              {outcome}
            </span>
          )}
          <span className="pix-pill" data-testid="lesson-source-type">
            {lesson.source_type}
          </span>
        </div>
        <p
          className="pix-row-sub line-clamp-3"
          data-testid="lesson-content"
          style={{ whiteSpace: "pre-wrap" }}
        >
          {lesson.content}
        </p>
        <div className="flex flex-wrap items-center gap-3" style={{ fontFamily: '"VT323", monospace', fontSize: 13 }}>
          <span className="flex items-center gap-1 text-muted-foreground" data-testid="lesson-created-at">
            <Calendar className="h-3 w-3" /> {formatDate(lesson.created_at)}
          </span>
          {lesson.tags.length > 0 && (
            <span className="flex flex-wrap items-center gap-1" data-testid="lesson-tags">
              <Tag className="h-3 w-3" />
              {lesson.tags.map((tag) => (
                <span key={tag} className="pix-tag">{tag}</span>
              ))}
            </span>
          )}
          {tradeId && (
            <a
              href={`#runs`}
              className="pix-link"
              data-testid="lesson-source-link"
              title={`Source run/trade ${tradeId}`}
            >
              Source run/trade
            </a>
          )}
        </div>
      </div>
    </PixelFrame>
  );
}

export function LearningView({ projectId }: { projectId: string }) {
  const { data, isLoading, isError } = useLearningLessons(projectId);
  const lessons = data?.items ?? [];
  const failed = isError;

  return (
    <div className="space-y-4" data-testid="learning-view">
      <PixelFrame tight>
        <div className="flex flex-wrap items-center gap-2" style={{ fontFamily: '"VT323", monospace', fontSize: 18 }}>
          <GraduationCap className="h-4 w-4" />
          <span>Learning</span>
          <span className="ml-1 text-xs opacity-60">— read-only trade lessons</span>
        </div>
        {/* Always-visible read-only safety framing (shown in every state). */}
        <div
          className="mt-2 flex flex-wrap items-center gap-1"
          data-testid="learning-safety-labels"
        >
          <span className="pix-pill">Advisory only</span>
          <span className="pix-pill">No order capability</span>
          <span className="pix-pill">Does not change validation_only</span>
          <span className="pix-pill">Fresh owner approval required for any future trade</span>
        </div>
      </PixelFrame>

      {isLoading ? (
        <PixelFrame>
          <div className="pix-empty" style={{ fontFamily: '"VT323", monospace' }}>
            Loading lessons…
          </div>
        </PixelFrame>
      ) : failed ? (
        <PixelFrame>
          <div className="pix-empty" style={{ fontFamily: '"VT323", monospace', color: "var(--pix-danger)" }}>
            Could not load lessons. Lessons are read-only and do not affect trading.
          </div>
        </PixelFrame>
      ) : lessons.length === 0 ? (
        <PixelFrame>
          <div className="pix-empty" data-testid="learning-empty-state">
            <BookOpen className="mx-auto mb-2 h-8 w-8" />
            <div className="space-y-1">
              <p>No lessons yet.</p>
              <p className="text-sm opacity-70">
                Lessons appear after closed trades / post-trade review. They are not automatically applied in this phase.
              </p>
            </div>
          </div>
        </PixelFrame>
      ) : (
        <>
          <PixelFrame tight>
            <div
              className="flex items-start gap-2"
              style={{ fontFamily: '"VT323", monospace', fontSize: 13, opacity: 0.85 }}
              data-testid="learning-read-only-note"
            >
              <BookOpen className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                Read-only. Lessons are not automatically applied to future runs in this phase.
                No edit, delete, apply, or injection controls are available.
              </span>
            </div>
          </PixelFrame>

          <div className="space-y-2">
            <SectionLabel>Trade Lessons ({lessons.length})</SectionLabel>
            {lessons.map((lesson) => (
              <LessonCard key={lesson.id} lesson={lesson} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
