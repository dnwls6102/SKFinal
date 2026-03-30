import { z } from "zod";

export const actionSchema = z.object({
  id: z.string(),
  type: z.enum(["apiCall", "dbQuery", "navigate", "showModal", "submitForm"]),
  label: z.string(),
  config: z.record(z.string(), z.any())
});

export const pageElementSchema = z.object({
  id: z.string(),
  type: z.enum(["heading", "text", "button", "card", "image"]),
  x: z.number(),
  y: z.number(),
  width: z.number(),
  height: z.number(),
  label: z.string(),
  description: z.string(),
  content: z.string(),
  background: z.string(),
  color: z.string(),
  borderRadius: z.number(),
  fontSize: z.number(),
  allowedActions: z.array(z.enum(["apiCall", "dbQuery", "navigate", "showModal", "submitForm"])),
  actions: z.array(actionSchema)
});

export const pageSettingsSchema = z.object({
  background: z.string(),
  pageSize: z.enum(["desktop", "tablet", "mobile"]),
  width: z.number(),
  minHeight: z.number()
});

export const builderProjectSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  selectedElementId: z.string().nullable(),
  settings: pageSettingsSchema,
  elements: z.array(pageElementSchema)
});
