"use client";

import { create } from "zustand";
import { blockCatalog } from "@/lib/catalog/blocks";
import { createEmptyProject } from "@/lib/runtime/create-empty-project";
import type { BuilderProject, ElementDefinition, PageElement, PageSize } from "@/types/builder";

type BuilderStore = {
  project: BuilderProject;
  selectedElementId: string | null;
  hydrateProject: (project: BuilderProject) => void;
  resetProject: (project?: BuilderProject) => void;
  addElement: (definition: ElementDefinition, x?: number, y?: number) => void;
  removeSelectedElement: () => void;
  duplicateSelectedElement: () => void;
  setSelectedElement: (elementId: string | null) => void;
  updateElementPosition: (elementId: string, x: number, y: number) => void;
  updateSelectedElement: (patch: Partial<PageElement>) => void;
  updateProjectMeta: (patch: Partial<BuilderProject>) => void;
  updatePageSettings: (patch: Partial<BuilderProject["settings"]>) => void;
  setPageSize: (pageSize: PageSize) => void;
};

const pageWidths: Record<PageSize, number> = {
  desktop: 1320,
  tablet: 900,
  mobile: 430
};

function buildElement(definition: ElementDefinition, index: number, x = 48, y = 180): PageElement {
  return {
    id: `${definition.type}-${index + 1}`,
    type: definition.type,
    x,
    y,
    width: definition.defaultProps.width,
    height: definition.defaultProps.height,
    label: definition.defaultProps.label,
    description: definition.defaultProps.description,
    content: definition.defaultProps.content,
    background: definition.type === "button" ? "#d9e7f6" : "#fffdf8",
    color: "#17212b",
    borderRadius: definition.type === "button" ? 0 : 16,
    fontSize: definition.type === "heading" ? 42 : 20,
    allowedActions: definition.allowedActions,
    actions: []
  };
}

export const useBuilderStore = create<BuilderStore>((set) => ({
  project: createEmptyProject(),
  selectedElementId: null,
  hydrateProject: (project) =>
    set({
      project,
      selectedElementId: project.selectedElementId
    }),
  resetProject: (project = createEmptyProject()) =>
    set({
      project,
      selectedElementId: project.selectedElementId
    }),
  addElement: (definition, x, y) =>
    set((state) => {
      const nextIndex = state.project.elements.length;
      const fallbackX = 40 + ((nextIndex % 3) * 180);
      const fallbackY = 180 + Math.floor(nextIndex / 3) * 120;
      const element = buildElement(definition, nextIndex, x ?? fallbackX, y ?? fallbackY);

      return {
        project: {
          ...state.project,
          selectedElementId: element.id,
          elements: [...state.project.elements, element]
        },
        selectedElementId: element.id
      };
    }),
  removeSelectedElement: () =>
    set((state) => {
      if (!state.selectedElementId) {
        return state;
      }

      return {
        selectedElementId: null,
        project: {
          ...state.project,
          selectedElementId: null,
          elements: state.project.elements.filter((element) => element.id !== state.selectedElementId)
        }
      };
    }),
  duplicateSelectedElement: () =>
    set((state) => {
      const current = state.project.elements.find((element) => element.id === state.selectedElementId);
      if (!current) {
        return state;
      }

      const duplicate: PageElement = {
        ...current,
        id: `${current.type}-${state.project.elements.length + 1}`,
        x: current.x + 28,
        y: current.y + 28
      };

      return {
        selectedElementId: duplicate.id,
        project: {
          ...state.project,
          selectedElementId: duplicate.id,
          elements: [...state.project.elements, duplicate]
        }
      };
    }),
  setSelectedElement: (elementId) =>
    set((state) => ({
      selectedElementId: elementId,
      project: {
        ...state.project,
        selectedElementId: elementId
      }
    })),
  updateElementPosition: (elementId, x, y) =>
    set((state) => ({
      project: {
        ...state.project,
        elements: state.project.elements.map((element) =>
          element.id === elementId ? { ...element, x, y } : element
        )
      }
    })),
  updateSelectedElement: (patch) =>
    set((state) => {
      if (!state.selectedElementId) {
        return state;
      }

      return {
        project: {
          ...state.project,
          elements: state.project.elements.map((element) =>
            element.id === state.selectedElementId ? { ...element, ...patch } : element
          )
        }
      };
    }),
  updateProjectMeta: (patch) =>
    set((state) => ({
      project: {
        ...state.project,
        ...patch
      }
    })),
  updatePageSettings: (patch) =>
    set((state) => ({
      project: {
        ...state.project,
        settings: {
          ...state.project.settings,
          ...patch
        }
      }
    })),
  setPageSize: (pageSize) =>
    set((state) => ({
      project: {
        ...state.project,
        settings: {
          ...state.project.settings,
          pageSize,
          width: pageWidths[pageSize]
        }
      }
    }))
}));

export const elementPalette = blockCatalog;
