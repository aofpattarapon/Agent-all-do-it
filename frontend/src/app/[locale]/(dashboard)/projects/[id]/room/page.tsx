"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import ProjectRoomView from "@/components/projects/project-room-view";

export default function PhaserRoomPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; locale: string }>;
  searchParams?: Promise<{ embed?: string }>;
}) {
  const { id } = use(params);
  const embedded = use((searchParams ?? Promise.resolve({ embed: undefined })) as Promise<{ embed?: string }>).embed === "1";
  const router = useRouter();

  useEffect(() => {
    if (!embedded) router.replace(`/projects/${id}#office`);
  }, [embedded, id, router]);

  if (!embedded) return null;
  return <ProjectRoomView projectId={id} embedded />;
}
