"use client";

import { actionCatalog } from "@/lib/catalog/actions";
import { useBuilderStore } from "@/store/builder-store";
import styles from "./builder.module.css";

export function RightInspector() {
  const selectedNode = useBuilderStore((state) =>
    state.project.nodes.find((node) => node.id === state.selectedNodeId)
  );
  const updateSelectedNode = useBuilderStore((state) => state.updateSelectedNode);

  if (!selectedNode) {
    return (
      <aside className={styles.panelRight}>
        <h2 className={styles.sectionTitle}>Inspector</h2>
        <div className={styles.emptyCard}>
          Select a block on the canvas to edit its label, description, and primary action.
        </div>
      </aside>
    );
  }

  return (
    <aside className={styles.panelRight}>
      <h2 className={styles.sectionTitle}>Inspector</h2>
      <div className={styles.fieldList}>
        <div className={styles.fieldCard}>
          <label className={styles.fieldLabel}>
            Label
            <input
              className={styles.input}
              value={selectedNode.data.label}
              onChange={(event) => updateSelectedNode({ label: event.target.value })}
            />
          </label>
        </div>
        <div className={styles.fieldCard}>
          <label className={styles.fieldLabel}>
            Description
            <textarea
              className={styles.input}
              value={selectedNode.data.description}
              onChange={(event) => updateSelectedNode({ description: event.target.value })}
            />
          </label>
        </div>
        <div className={styles.fieldCard}>
          <label className={styles.fieldLabel}>
            Primary Action
            <select
              className={styles.select}
              value={selectedNode.data.actions[0]?.type ?? ""}
              onChange={(event) => {
                const nextAction = actionCatalog.find((action) => action.type === event.target.value);
                if (!nextAction) {
                  return;
                }

                updateSelectedNode({
                  actions: [
                    {
                      id: `${selectedNode.id}-${nextAction.type}`,
                      type: nextAction.type,
                      label: nextAction.label,
                      config: nextAction.defaultConfig
                    }
                  ]
                });
              }}
            >
              <option value="">No action</option>
              {actionCatalog
                .filter((action) => selectedNode.data.allowedActions.includes(action.type))
                .map((action) => (
                  <option key={action.type} value={action.type}>
                    {action.label}
                  </option>
                ))}
            </select>
          </label>
        </div>
      </div>
    </aside>
  );
}
