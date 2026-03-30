import type { BuilderProject } from "@/types/builder";

export function createEmptyProject(): BuilderProject {
  return {
    id: "project-root",
    name: "Untitled Prototype",
    description: "New prototype",
    selectedNodeId: null,
    nodes: []
  };
}
