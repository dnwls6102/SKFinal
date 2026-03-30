import { builderProjectSchema } from "@/lib/schemas/project-schema";
import type { BuilderProject } from "@/types/builder";

export const PROJECT_STORAGE_KEY = "prototype-builder-project";

export function loadProjectFromStorage(): BuilderProject | null {
  if (typeof window === "undefined") {
    return null;
  }

  const raw = window.localStorage.getItem(PROJECT_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  const parsed = builderProjectSchema.safeParse(JSON.parse(raw));
  return parsed.success ? parsed.data : null;
}

export function saveProjectToStorage(project: BuilderProject) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(PROJECT_STORAGE_KEY, JSON.stringify(project));
}
