import type { BuilderProject } from "@/types/builder";

export function createEmptyProject(): BuilderProject {
  return {
    id: "project-root",
    name: "Untitled Prototype",
    description: "New prototype",
    selectedElementId: null,
    settings: {
      background: "#f5f1e8",
      pageSize: "desktop",
      width: 1320,
      minHeight: 880
    },
    elements: [
      {
        id: "page-title",
        type: "heading",
        x: 18,
        y: 18,
        width: 720,
        height: 84,
        label: "Page Title",
        description: "Top title block",
        content: "Prototype Builder",
        background: "#d9e7f6",
        color: "#17212b",
        borderRadius: 0,
        fontSize: 48,
        allowedActions: ["navigate", "showModal"],
        actions: []
      }
    ]
  };
}
