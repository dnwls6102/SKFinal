import type { BuilderProject } from "@/types/builder";

export function createDemoProject(prompt: string): BuilderProject {
  return {
    id: "demo-project",
    name: "AI Generated Draft",
    description: prompt,
    selectedNodeId: null,
    nodes: [
      {
        id: "hero-copy",
        position: { x: 80, y: 80 },
        data: {
          blockType: "text",
          label: "Service Overview",
          description: `Introduce the purpose and main flow for: ${prompt}.`,
          allowedActions: ["navigate", "showModal"],
          actions: []
        }
      },
      {
        id: "summary-card",
        position: { x: 410, y: 80 },
        data: {
          blockType: "rectangle",
          label: "Key Metrics",
          description: "Show major counts such as daily volume, response rate, and pending work.",
          allowedActions: ["apiCall", "navigate"],
          actions: [
            {
              id: "summary-card-api",
              type: "apiCall",
              label: "API Connect",
              config: { endpoint: "/api/demo/kpi", method: "GET" }
            }
          ]
        }
      },
      {
        id: "data-table",
        position: { x: 80, y: 300 },
        data: {
          blockType: "table",
          label: "Record Table",
          description: "List the main entities and their current status fields.",
          allowedActions: ["apiCall", "dbQuery"],
          actions: [
            {
              id: "data-table-db",
              type: "dbQuery",
              label: "DB Query",
              config: { source: "inquiries", limit: 20 }
            }
          ]
        }
      },
      {
        id: "chat-panel",
        position: { x: 490, y: 320 },
        data: {
          blockType: "chat",
          label: "Operator Chat Assist",
          description: "Let operators test common prompts or preview draft responses.",
          allowedActions: ["apiCall", "submitForm"],
          actions: [
            {
              id: "chat-panel-submit",
              type: "submitForm",
              label: "Submit Form",
              config: { endpoint: "/api/demo/chat", method: "POST" }
            }
          ]
        }
      }
    ]
  };
}
