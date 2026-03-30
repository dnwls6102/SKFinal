"use client";

import { blockCatalog } from "@/lib/catalog/blocks";
import { useBuilderStore } from "@/store/builder-store";
import styles from "./builder.module.css";

export function LeftPalette() {
  const addNodeFromDefinition = useBuilderStore((state) => state.addNodeFromDefinition);

  return (
    <aside className={styles.panel}>
      <h2 className={styles.sectionTitle}>Block Palette</h2>
      <p className={styles.muted}>The demo exposes only fixed block types. Each block carries its own allowed action set.</p>
      <div className={styles.paletteList}>
        {blockCatalog.map((block) => (
          <button
            key={block.type}
            type="button"
            className={styles.paletteItem}
            onClick={() => addNodeFromDefinition(block)}
          >
            <span>
              <span className={styles.paletteName}>{block.label}</span>
              <span className={styles.paletteDesc}>{block.description}</span>
            </span>
            <span className={styles.badge}>{block.type}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
