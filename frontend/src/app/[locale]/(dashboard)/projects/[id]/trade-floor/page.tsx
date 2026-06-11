"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import ProjectTradeFloorView from "@/components/projects/project-trade-floor-view";

export default function ProjectTradeFloorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ embed?: string }>;
}) {
  const { id } = use(params);
  const embedded =
    use((searchParams ?? Promise.resolve({ embed: undefined })) as Promise<{ embed?: string }>).embed === "1";
  const router = useRouter();

  useEffect(() => {
    if (!embedded) router.replace(`/projects/${id}#trade-floor`);
  }, [embedded, id, router]);

  if (!embedded) return null;
  return <ProjectTradeFloorView projectId={id} />;
}
