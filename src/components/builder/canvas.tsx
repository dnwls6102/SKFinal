"use client";

import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Node,
  type NodeChange,
  type NodeTypes,
  type OnNodesChange
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GenericNode } from "@/components/builder/nodes/generic-node";
import { useBuilderStore } from "@/store/builder-store";
import type { BuilderNodeData } from "@/types/builder";
import styles from "./builder.module.css";

type CanvasNode = Node<BuilderNodeData, "builderBlock">;

const nodeTypes = {
  builderBlock: GenericNode
} satisfies NodeTypes;

export function BuilderCanvas() {
  const project = useBuilderStore((state) => state.project);
  const setSelectedNode = useBuilderStore((state) => state.setSelectedNode);
  const updateNodePosition = useBuilderStore((state) => state.updateNodePosition);

  const nodes: CanvasNode[] = project.nodes.map((node) => ({
    id: node.id,
    type: "builderBlock",
    position: node.position,
    data: node.data,
    selected: node.id === project.selectedNodeId
  }));

  const onNodesChange: OnNodesChange = (changes) => {
    for (const change of changes as NodeChange<CanvasNode>[]) {
      if (change.type === "position" && change.position) {
        updateNodePosition(change.id, change.position);
      }

      if (change.type === "select") {
        setSelectedNode(change.selected ? change.id : null);
      }
    }
  };

  return (
    <div className={styles.canvas}>
      <ReactFlow
        fitView
        nodes={nodes}
        edges={[]}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(_, node) => setSelectedNode(node.id)}
      >
        <Background gap={28} size={1} />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>
    </div>
  );
}
