import { apiRequest } from "@/lib/api-client";

export interface Category {
  id: string;
  name: string;
  icon: string;
  color: string;
  budget_minor: number | null;
  parent_id: string | null;
  is_system: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CategoryCreateInput {
  name: string;
  icon: string;
  color: string;
  budget_minor?: number | null;
  parent_id?: string | null;
}

export interface CategoryUpdateInput {
  name?: string;
  icon?: string;
  color?: string;
  budget_minor?: number | null;
  parent_id?: string | null;
  clear_parent?: boolean;
}

export async function listCategories(
  accessToken: string,
  options: { includeInactive?: boolean } = {}
): Promise<Category[]> {
  const query = options.includeInactive ? "?include_inactive=true" : "";
  return apiRequest<Category[]>(`/api/v1/categories${query}`, { accessToken });
}

export async function createCategory(
  accessToken: string,
  input: CategoryCreateInput
): Promise<Category> {
  return apiRequest<Category>("/api/v1/categories", { method: "POST", accessToken, body: input });
}

export async function updateCategory(
  accessToken: string,
  categoryId: string,
  input: CategoryUpdateInput
): Promise<Category> {
  return apiRequest<Category>(`/api/v1/categories/${categoryId}`, {
    method: "PUT",
    accessToken,
    body: input,
  });
}

export async function archiveCategory(accessToken: string, categoryId: string): Promise<void> {
  await apiRequest(`/api/v1/categories/${categoryId}`, { method: "DELETE", accessToken });
}
