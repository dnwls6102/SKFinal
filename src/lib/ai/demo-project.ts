import type { BuilderProject } from "@/types/builder";

export function createDemoProject(prompt: string): BuilderProject {
  return {
    id: "demo-project",
    name: "AI Generated Draft",
    description: prompt,
    selectedElementId: null,
    settings: {
      background: "#f7f3ea",
      pageSize: "desktop",
      width: 1320,
      minHeight: 920
    },
    elements: [
      {
        id: "title-block",
        type: "heading",
        x: 18,
        y: 18,
        width: 760,
        height: 84,
        label: "Project Title",
        description: "Main page title",
        content: prompt,
        background: "#d9e7f6",
        color: "#15202b",
        borderRadius: 0,
        fontSize: 42,
        allowedActions: ["navigate", "showModal"],
        actions: []
      },
      {
        id: "page-chip-1",
        type: "button",
        x: 18,
        y: 108,
        width: 260,
        height: 46,
        label: "Background Control",
        description: "Change page background",
        content: "Background",
        background: "#d9e7f6",
        color: "#17212b",
        borderRadius: 0,
        fontSize: 20,
        allowedActions: ["showModal"],
        actions: []
      },
      {
        id: "page-chip-2",
        type: "button",
        x: 278,
        y: 108,
        width: 320,
        height: 46,
        label: "Page Size Control",
        description: "Change page size",
        content: "Page Size",
        background: "#d9e7f6",
        color: "#17212b",
        borderRadius: 0,
        fontSize: 20,
        allowedActions: ["showModal"],
        actions: []
      },
      {
        id: "page-card",
        type: "card",
        x: 18,
        y: 210,
        width: 420,
        height: 240,
        label: "Intro Card",
        description: "Primary content card",
        content: `This prototype is focused on ${prompt}. Drag elements directly on the page and edit them in place.`,
        background: "#fffdf8",
        color: "#1c2733",
        borderRadius: 16,
        fontSize: 22,
        allowedActions: ["apiCall", "submitForm"],
        actions: []
      }
    ]
  };
}
