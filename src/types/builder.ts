export type ActionType = "apiCall" | "dbQuery" | "navigate" | "showModal" | "submitForm";
export type BlockType = "text" | "table" | "rectangle" | "chat" | "scrollSection";

export type ActionDefinition = {
  type: ActionType;
  label: string;
  description: string;
  defaultConfig: Record<string, string | number>;
};

export type BlockDefinition = {
  type: BlockType;
  label: string;
  description: string;
  defaultProps: {
    label: string;
    description: string;
  };
  allowedActions: ActionType[];
};

export type BuilderAction = {
  id: string;
  type: ActionType;
  label: string;
  config: Record<string, unknown>;
};

export type BuilderNodeData = {
  blockType: BlockType;
  label: string;
  description: string;
  allowedActions: ActionType[];
  actions: BuilderAction[];
};

export type BuilderNode = {
  id: string;
  position: {
    x: number;
    y: number;
  };
  data: BuilderNodeData;
};

export type BuilderProject = {
  id: string;
  name: string;
  description: string;
  selectedNodeId: string | null;
  nodes: BuilderNode[];
};
