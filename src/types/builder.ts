export type ActionType = "apiCall" | "dbQuery" | "navigate" | "showModal" | "submitForm";
export type ElementType = "heading" | "text" | "button" | "card" | "image";
export type PageSize = "desktop" | "tablet" | "mobile";

export type ActionDefinition = {
  type: ActionType;
  label: string;
  description: string;
  defaultConfig: Record<string, string | number>;
};

export type ElementDefinition = {
  type: ElementType;
  label: string;
  description: string;
  defaultProps: {
    label: string;
    description: string;
    content: string;
    width: number;
    height: number;
  };
  allowedActions: ActionType[];
};

export type PageElementAction = {
  id: string;
  type: ActionType;
  label: string;
  config: Record<string, unknown>;
};

export type PageElement = {
  id: string;
  type: ElementType;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  description: string;
  content: string;
  background: string;
  color: string;
  borderRadius: number;
  fontSize: number;
  allowedActions: ActionType[];
  actions: PageElementAction[];
};

export type PageSettings = {
  background: string;
  pageSize: PageSize;
  width: number;
  minHeight: number;
};

export type BuilderProject = {
  id: string;
  name: string;
  description: string;
  selectedElementId: string | null;
  settings: PageSettings;
  elements: PageElement[];
};
