"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { CategoryForm } from "@/components/categories/category-form";
import { CategoryRow } from "@/components/categories/category-row";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import {
  archiveCategory,
  createCategory,
  listCategories,
  updateCategory,
  type Category,
  type CategoryCreateInput,
  type CategoryUpdateInput,
} from "@/lib/categories";

type ModalState = { mode: "create" } | { mode: "edit"; category: Category } | null;

export default function CategoriesPage() {
  const { accessToken } = useAuth();
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void listCategories(accessToken)
      .then((data) => {
        if (!isMounted) return;
        setCategories(data);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof ApiError ? err.message : "Failed to load categories.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  const { topLevel, childrenByParent } = useMemo(() => {
    const all = categories ?? [];
    const byId = new Map(all.map((c) => [c.id, c]));
    const top: Category[] = [];
    const children = new Map<string, Category[]>();

    for (const category of all) {
      if (category.parent_id && byId.has(category.parent_id)) {
        const siblings = children.get(category.parent_id) ?? [];
        siblings.push(category);
        children.set(category.parent_id, siblings);
      } else {
        top.push(category);
      }
    }
    return { topLevel: top, childrenByParent: children };
  }, [categories]);

  async function handleCreate(input: CategoryCreateInput | CategoryUpdateInput) {
    if (!accessToken) return;
    await createCategory(accessToken, input as CategoryCreateInput);
    setModalState(null);
    reload();
  }

  async function handleUpdate(categoryId: string, input: CategoryCreateInput | CategoryUpdateInput) {
    if (!accessToken) return;
    await updateCategory(accessToken, categoryId, input as CategoryUpdateInput);
    setModalState(null);
    reload();
  }

  async function handleDelete(categoryId: string) {
    if (!accessToken) return;
    await archiveCategory(accessToken, categoryId);
    reload();
  }

  const parentOptions = (categories ?? []).filter(
    (c) => modalState?.mode !== "edit" || c.id !== modalState.category.id
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Categories</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Default categories are shared and can&apos;t be edited. Add your own for anything
            specific to you.
          </p>
        </div>
        <Button className="self-start sm:self-auto" onClick={() => setModalState({ mode: "create" })}>
          + Add category
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button
            type="button"
            onClick={reload}
            className="font-medium underline"
          >
            Try again
          </button>
        </div>
      )}

      {categories === null && !error && (
        <div className="flex flex-col gap-2">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      )}

      {categories !== null && (
        <Card>
          {topLevel.length === 0 ? (
            <p className="py-6 text-center text-sm text-zinc-600 dark:text-zinc-400">
              No categories yet.
            </p>
          ) : (
            topLevel
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((category) => (
                <div key={category.id}>
                  <CategoryRow
                    category={category}
                    isChild={false}
                    onEdit={() => setModalState({ mode: "edit", category })}
                    onDelete={() => handleDelete(category.id)}
                  />
                  {(childrenByParent.get(category.id) ?? [])
                    .sort((a, b) => a.name.localeCompare(b.name))
                    .map((child) => (
                      <CategoryRow
                        key={child.id}
                        category={child}
                        isChild
                        onEdit={() => setModalState({ mode: "edit", category: child })}
                        onDelete={() => handleDelete(child.id)}
                      />
                    ))}
                </div>
              ))
          )}
        </Card>
      )}

      {modalState?.mode === "create" && (
        <Modal title="Add category" onClose={() => setModalState(null)}>
          <CategoryForm
            parentOptions={parentOptions}
            onSubmit={handleCreate}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}

      {modalState?.mode === "edit" && (
        <Modal title="Edit category" onClose={() => setModalState(null)}>
          <CategoryForm
            category={modalState.category}
            parentOptions={parentOptions}
            onSubmit={(input) => handleUpdate(modalState.category.id, input)}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}
    </div>
  );
}
