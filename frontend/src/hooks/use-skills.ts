"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export interface Skill {
  id: string;
  source: string;
  slug: string | null;
  name: string;
  description: string | null;
  category: string;
  tags: string[];
  popularity: number;
  is_active: boolean;
}

export function useSkills() {
  const { data: skills, isLoading } = useQuery<Skill[]>({
    queryKey: ["skills"],
    queryFn: () => apiClient.get<Skill[]>("/skills?limit=500"),
  });

  const { data: categories } = useQuery<string[]>({
    queryKey: ["skill-categories"],
    queryFn: () => apiClient.get<string[]>("/skills/categories"),
  });

  return { skills: skills ?? [], categories: categories ?? [], isLoading };
}
