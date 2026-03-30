import type { ActionDefinition } from "@/types/builder";

export const actionCatalog: ActionDefinition[] = [
  {
    type: "apiCall",
    label: "API Connect",
    description: "Connect to a REST API or internal route.",
    defaultConfig: {
      endpoint: "/api/demo",
      method: "GET"
    }
  },
  {
    type: "dbQuery",
    label: "DB Query",
    description: "Connect to a demo query or mock response source.",
    defaultConfig: {
      source: "users",
      limit: 20
    }
  },
  {
    type: "navigate",
    label: "Navigate",
    description: "Move to another screen or detail view.",
    defaultConfig: {
      target: "/detail"
    }
  },
  {
    type: "showModal",
    label: "Open Modal",
    description: "Open a detail or confirmation modal.",
    defaultConfig: {
      modalId: "default-modal"
    }
  },
  {
    type: "submitForm",
    label: "Submit Form",
    description: "Send form input to a server action or API.",
    defaultConfig: {
      endpoint: "/api/submit",
      method: "POST"
    }
  }
];
