import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export interface KnowledgeTemplate {
  id: string;
  source: string;
  source_key: string;
  name: string;
  description: string | null;
  category: string;
  subcategory: string | null;
  tags: string[];
  popularity: number;
  is_active: boolean;
}

export interface KnowledgeTemplateDetail extends KnowledgeTemplate {
  content: string;
}

export function useKnowledgeTemplates() {
  const { data: templates, isLoading: isLoadingTemplates } = useQuery<KnowledgeTemplate[]>({
    queryKey: ["knowledge-templates"],
    queryFn: () => apiClient.get<KnowledgeTemplate[]>("/knowledge-templates?limit=500"),
  });

  const { data: categories, isLoading: isLoadingCategories } = useQuery<string[]>({
    queryKey: ["knowledge-template-categories"],
    queryFn: () => apiClient.get<string[]>("/knowledge-templates/categories"),
  });

  return {
    templates: templates ?? [],
    categories: categories ?? [],
    isLoading: isLoadingTemplates || isLoadingCategories,
  };
}
