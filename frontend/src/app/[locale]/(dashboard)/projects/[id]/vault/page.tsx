"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import ProjectVaultView from "@/components/projects/project-vault-view";

export default function ProjectVaultPage({
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
    if (!embedded) router.replace(`/projects/${id}#vault`);
  }, [embedded, id, router]);

  if (!embedded) return null;
  return <ProjectVaultView projectId={id} embedded />;
}
