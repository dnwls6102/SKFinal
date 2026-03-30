import type { ElementDefinition } from "@/types/builder";

export const blockCatalog: ElementDefinition[] = [
  {
    type: "heading",
    label: "Heading",
    description: "Use for page titles and section headers.",
    defaultProps: {
      label: "Page Heading",
      description: "A large text block for the top of the page.",
      content: "Prototype Builder",
      width: 520,
      height: 72
    },
    allowedActions: ["navigate", "showModal"]
  },
  {
    type: "text",
    label: "Text Box",
    description: "Use for body text, labels, and short descriptions.",
    defaultProps: {
      label: "Text Block",
      description: "A text area for supporting copy.",
      content: "Add supporting text here.",
      width: 360,
      height: 120
    },
    allowedActions: ["navigate", "showModal"]
  },
  {
    type: "button",
    label: "Button",
    description: "Use for call-to-action buttons and menu chips.",
    defaultProps: {
      label: "Action Button",
      description: "A simple clickable action area.",
      content: "Open Details",
      width: 220,
      height: 56
    },
    allowedActions: ["apiCall", "navigate"]
  },
  {
    type: "card",
    label: "Card",
    description: "Use for boxes, panels, and grouped content zones.",
    defaultProps: {
      label: "Card Panel",
      description: "A rectangular panel that can highlight content.",
      content: "Drop content here.",
      width: 320,
      height: 180
    },
    allowedActions: ["apiCall", "submitForm"]
  },
  {
    type: "image",
    label: "Image",
    description: "Use for image placeholders, thumbnails, and visual blocks.",
    defaultProps: {
      label: "Image Placeholder",
      description: "A visual placeholder block.",
      content: "Image",
      width: 280,
      height: 180
    },
    allowedActions: ["navigate", "showModal"]
  }
];
