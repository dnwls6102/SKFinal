"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { BuilderCanvas } from "@/components/builder/canvas";
import { FloatingRemote } from "@/components/builder/floating-remote";
import { createEmptyProject } from "@/lib/runtime/create-empty-project";
import { loadProjectFromStorage, saveProjectToStorage } from "@/lib/runtime/storage";
import { useBuilderStore } from "@/store/builder-store";
import styles from "./builder.module.css";

export function BuilderShell() {
  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState("Ask AI for a draft project or add blocks directly from the palette.");
  const [isPending, startTransition] = useTransition();
  const hasHydrated = useRef(false);
  const project = useBuilderStore((state) => state.project);
  const hydrateProject = useBuilderStore((state) => state.hydrateProject);
  const resetProject = useBuilderStore((state) => state.resetProject);

  useEffect(() => {
    if (hasHydrated.current) {
      return;
    }

    const savedProject = loadProjectFromStorage();
    if (savedProject) {
      hydrateProject(savedProject);
      setStatus("Recovered the previous draft from localStorage.");
    }

    hasHydrated.current = true;
  }, [hydrateProject]);

  useEffect(() => {
    if (!hasHydrated.current) {
      return;
    }

    saveProjectToStorage(project);
  }, [project]);

  const handleGenerate = () => {
    startTransition(async () => {
      setStatus("AI is composing a block layout draft.");

      try {
        const response = await fetch("/api/ai-generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt })
        });

        if (!response.ok) {
          throw new Error("failed_to_generate");
        }

        const data = await response.json();
        hydrateProject(data.project);
        setStatus(
          data.mode === "live"
            ? "AI placed a live draft on the canvas."
            : "No OpenAI key found, so the canvas was filled with a mock draft."
        );
      } catch {
        setStatus("Draft generation failed. Reverting to an empty project.");
        resetProject(createEmptyProject());
      }
    });
  };

  const handleReset = () => {
    resetProject(createEmptyProject());
    setStatus("Reset to an empty project.");
  };

  return (
    <main className={styles.page}>
      <section className={styles.viewport}>
        <div className={styles.floatingPrompt}>
          <h1>Prototype Builder</h1>
          <p>The whole page is editable now. Drag real page elements onto the canvas and tune them with the remote.</p>
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Example: hero landing page, admin dashboard shell, FAQ intro page"
            className={styles.textarea}
          />
          <div className={styles.promptActions}>
            <button type="button" onClick={handleGenerate} disabled={isPending} className={styles.primaryButton}>
              {isPending ? "Generating..." : "Generate with AI"}
            </button>
            <button type="button" onClick={handleReset} className={styles.secondaryButton}>
              New Project
            </button>
          </div>
          <p className={styles.status}>{status}</p>
        </div>
      </section>

      <BuilderCanvas />
      <FloatingRemote />
    </main>
  );
}
