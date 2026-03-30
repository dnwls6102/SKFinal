"use client";

import { create } from "zustand";
import { createEmptyProject } from "@/lib/runtime/create-empty-project";
import type { BlockDefinition, BuilderNode, BuilderProject } from "@/types/builder";

type BuilderStore = {
  project: BuilderProject;
  selectedNodeId: string | null;
  hydrateProject: (project: BuilderProject) => void;
  resetProject: (project?: BuilderProject) => void;
  addNodeFromDefinition: (definition: BlockDefinition) => void;
  setSelectedNode: (nodeId: string | null) => void;
  updateNodePosition: (nodeId: string, position: BuilderNode["position"]) => void;
  updateSelectedNode: (patch: Partial<BuilderNode["data"]>) => void;
};

export const useBuilderStore = create<BuilderStore>((set) => ({
  project: createEmptyProject(),
  selectedNodeId: null,
  hydrateProject: (project) =>
    set({
      project,
      selectedNodeId: project.selectedNodeId
    }),
  resetProject: (project = createEmptyProject()) =>
    set({
      project,
      selectedNodeId: project.selectedNodeId
    }),
  addNodeFromDefinition: (definition) =>
    set((state) => {
      const nextIndex = state.project.nodes.length;
      const id = `${definition.type}-${nextIndex + 1}`;
      const node: BuilderNode = {
        id,
        position: {
          x: 60 + ((nextIndex % 3) * 240),
          y: 60 + Math.floor(nextIndex / 3) * 180
        },
        data: {
          blockType: definition.type,
          label: definition.defaultProps.label,
          description: definition.defaultProps.description,
          allowedActions: definition.allowedActions,
          actions: []
        }
      };

      return {
        project: {
          ...state.project,
          nodes: [...state.project.nodes, node],
          selectedNodeId: id
        },
        selectedNodeId: id
      };
    }),
  setSelectedNode: (nodeId) =>
    set((state) => ({
      selectedNodeId: nodeId,
      project: {
        ...state.project,
        selectedNodeId: nodeId
      }
    })),
  updateNodePosition: (nodeId, position) =>
    set((state) => ({
      project: {
        ...state.project,
        nodes: state.project.nodes.map((node) =>
          node.id === nodeId ? { ...node, position } : node
        )
      }
    })),
  updateSelectedNode: (patch) =>
    set((state) => {
      if (!state.selectedNodeId) {
        return state;
      }

      return {
        project: {
          ...state.project,
          nodes: state.project.nodes.map((node) =>
            node.id === state.selectedNodeId
              ? {
                  ...node,
                  data: {
                    ...node.data,
                    ...patch
                  }
                }
              : node
          )
        }
      };
    })
}));
