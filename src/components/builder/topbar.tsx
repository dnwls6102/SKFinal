"use client";

import { useBuilderStore } from "@/store/builder-store";
import styles from "./builder.module.css";

export function TopBar() {
  const project = useBuilderStore((state) => state.project);
  const summary = {
    blocks: project.nodes.length,
    actions: project.nodes.reduce((count, node) => count + node.data.actions.length, 0)
  };

  return (
    <div className={styles.topBar}>
      <div>
        <strong>{project.name}</strong>
      </div>
      <div className={styles.topBarMeta}>
        <span>Blocks {summary.blocks}</span>
        <span>Actions {summary.actions}</span>
        <span>Storage local-first</span>
      </div>
    </div>
  );
}
