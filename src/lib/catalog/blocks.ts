import type { BlockDefinition } from "@/types/builder";

export const blockCatalog: BlockDefinition[] = [
  {
    type: "text",
    label: "Text Box",
    description: "Use for intros, banners, and explanatory copy.",
    defaultProps: {
      label: "New Text Block",
      description: "Write a short message that explains the intent of the screen."
    },
    allowedActions: ["navigate", "showModal"]
  },
  {
    type: "table",
    label: "Table",
    description: "Display structured records such as users, inquiries, or orders.",
    defaultProps: {
      label: "Member List",
      description: "A table block wired for sample rows and columns."
    },
    allowedActions: ["apiCall", "dbQuery"]
  },
  {
    type: "rectangle",
    label: "Rectangle Card",
    description: "Use for KPI summaries and highlighted callouts.",
    defaultProps: {
      label: "Summary Card",
      description: "Show a key metric or state value."
    },
    allowedActions: ["apiCall", "navigate"]
  },
  {
    type: "chat",
    label: "Chat Box",
    description: "Useful for FAQ, support, or AI-response demos.",
    defaultProps: {
      label: "Support Chatbot",
      description: "Collect a prompt and show a response thread."
    },
    allowedActions: ["apiCall", "submitForm"]
  },
  {
    type: "scrollSection",
    label: "Scroll Section",
    description: "Best for long-form landing content or guided narratives.",
    defaultProps: {
      label: "Story Section",
      description: "Reveal content progressively as the user scrolls."
    },
    allowedActions: ["navigate", "showModal"]
  }
];
