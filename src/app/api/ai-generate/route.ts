import { NextResponse } from "next/server";
import OpenAI from "openai";
import { zodTextFormat } from "openai/helpers/zod";
import { actionCatalog } from "@/lib/catalog/actions";
import { blockCatalog } from "@/lib/catalog/blocks";
import { createDemoProject } from "@/lib/ai/demo-project";
import { builderProjectSchema } from "@/lib/schemas/project-schema";

const promptPrelude = `
You are an interaction planner for a visual web prototype builder.
Only use the provided block types and action types.
Keep the output practical for a quick MVP prototype.
Prefer 3-6 blocks with a clean layout and realistic mock data.
`;

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const userPrompt =
    typeof body?.prompt === "string" && body.prompt.trim().length > 0
      ? body.prompt.trim()
      : "A dashboard that classifies customer inquiries and tracks response status";

  const apiKey = process.env.OPENAI_API_KEY;

  if (!apiKey) {
    return NextResponse.json({
      project: createDemoProject(userPrompt),
      mode: "mock"
    });
  }

  const client = new OpenAI({ apiKey });
  const response = await client.responses.parse({
    model: "gpt-5.4-mini",
    input: [
      {
        role: "system",
        content: [{ type: "input_text", text: promptPrelude }]
      },
      {
        role: "user",
        content: [
          {
            type: "input_text",
            text: [
              `User request: ${userPrompt}`,
              `Available blocks: ${JSON.stringify(blockCatalog)}`,
              `Available actions: ${JSON.stringify(actionCatalog)}`
            ].join("\n")
          }
        ]
      }
    ],
    text: {
      format: zodTextFormat(builderProjectSchema, "builder_project")
    }
  });

  return NextResponse.json({
    project: response.output_parsed,
    mode: "live"
  });
}
