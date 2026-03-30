import { z } from "zod";

export const actionSchema = z.object({
  id: z.string(),
  type: z.enum(["apiCall", "dbQuery", "navigate", "showModal", "submitForm"]),
  label: z.string(),
  config: z.record(z.string(), z.any())
});

export const builderNodeDataSchema = z.object({
  blockType: z.enum(["text", "table", "rectangle", "chat", "scrollSection"]),
  label: z.string(),
  description: z.string(),
  allowedActions: z.array(z.enum(["apiCall", "dbQuery", "navigate", "showModal", "submitForm"])),
  actions: z.array(actionSchema)
});

export const builderNodeSchema = z.object({
  id: z.string(),
  position: z.object({
    x: z.number(),
    y: z.number()
  }),
  data: builderNodeDataSchema
});

export const builderProjectSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  selectedNodeId: z.string().nullable(),
  nodes: z.array(builderNodeSchema)
});
