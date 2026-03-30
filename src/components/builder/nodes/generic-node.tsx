"use client";

import type { Node, NodeProps } from "@xyflow/react";
import type { BuilderNodeData } from "@/types/builder";
import styles from "@/components/builder/builder.module.css";

type GenericBuilderNode = Node<BuilderNodeData, "builderBlock">;

export function GenericNode({ data }: NodeProps<GenericBuilderNode>) {
  const primaryAction = data.actions[0];

  return (
    <div className={styles.nodeCard}>
      <div className={styles.nodeHeader}>
        <span>{data.blockType}</span>
        {primaryAction ? <span>{primaryAction.label}</span> : <span>no action</span>}
      </div>
      <div className={styles.nodeBody}>
        <h3 className={styles.nodeTitle}>{data.label}</h3>
        <p className={styles.nodeText}>{data.description}</p>
      </div>
    </div>
  );
}
