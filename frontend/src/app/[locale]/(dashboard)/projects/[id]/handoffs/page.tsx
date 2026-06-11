"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import ProjectHandoffsView from "@/components/projects/project-handoffs-view";

export default function ProjectHandoffsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ embed?: string }>;
}) {
  const { id } = use(params);
  const embedded = use((searchParams ?? Promise.resolve({ embed: undefined })) as Promise<{ embed?: string }>).embed === "1";
  const router = useRouter();

  useEffect(() => {
    if (!embedded) router.replace(`/projects/${id}#handoffs`);
  }, [embedded, id, router]);

  if (!embedded) return null;
  return <ProjectHandoffsView projectId={id} embedded />;
}
