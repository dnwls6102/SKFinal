"use client";

import { useState } from "react";
import { elementPalette, useBuilderStore } from "@/store/builder-store";
import styles from "./builder.module.css";

const pageBackgrounds = ["#f5f1e8", "#f0f4ff", "#f7efe8", "#eef5ec", "#ffffff"];
const accentBackgrounds = ["#d9e7f6", "#fee6cf", "#dfead5", "#f9dfe5", "#fffdf8"];

export function FloatingRemote() {
  const [open, setOpen] = useState(true);
  const project = useBuilderStore((state) => state.project);
  const selectedElement = useBuilderStore((state) =>
    state.project.elements.find((element) => element.id === state.selectedElementId)
  );
  const addElement = useBuilderStore((state) => state.addElement);
  const updateProjectMeta = useBuilderStore((state) => state.updateProjectMeta);
  const updatePageSettings = useBuilderStore((state) => state.updatePageSettings);
  const setPageSize = useBuilderStore((state) => state.setPageSize);
  const updateSelectedElement = useBuilderStore((state) => state.updateSelectedElement);
  const removeSelectedElement = useBuilderStore((state) => state.removeSelectedElement);
  const duplicateSelectedElement = useBuilderStore((state) => state.duplicateSelectedElement);

  return (
    <div className={styles.remote}>
      <button type="button" className={styles.remoteToggle} onClick={() => setOpen((value) => !value)}>
        {open ? "Menu / Hide" : "Menu / Open"}
      </button>

      {open ? (
        <aside className={styles.remotePanel}>
          <h2>Remote Controls</h2>
          <p>Drag from here onto the page or use quick actions below.</p>

          <section className={styles.remoteSection}>
            <h3 className={styles.remoteSectionTitle}>Add Elements</h3>
            <div className={styles.remoteAddGrid}>
              {elementPalette.map((definition) => (
                <button
                  key={definition.type}
                  type="button"
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData("application/x-builder-element", definition.type);
                  }}
                  onClick={() => addElement(definition)}
                  className={styles.remoteAddButton}
                >
                  <strong>{definition.label}</strong>
                  <div>{definition.description}</div>
                </button>
              ))}
            </div>
          </section>

          <section className={styles.remoteSection}>
            <h3 className={styles.remoteSectionTitle}>Page</h3>
            <div className={styles.remoteField}>
              <label className={styles.remoteLabel}>Project Name</label>
              <input
                className={styles.input}
                value={project.name}
                onChange={(event) => updateProjectMeta({ name: event.target.value })}
              />
            </div>
            <div className={styles.remoteField}>
              <label className={styles.remoteLabel}>Page Size</label>
              <select
                className={styles.select}
                value={project.settings.pageSize}
                onChange={(event) => setPageSize(event.target.value as "desktop" | "tablet" | "mobile")}
              >
                <option value="desktop">Desktop</option>
                <option value="tablet">Tablet</option>
                <option value="mobile">Mobile</option>
              </select>
            </div>
            <div className={styles.remoteField}>
              <label className={styles.remoteLabel}>Background</label>
              <div className={styles.colorRow}>
                {pageBackgrounds.map((color) => (
                  <button
                    key={color}
                    type="button"
                    className={styles.colorSwatch}
                    style={{ background: color }}
                    onClick={() => updatePageSettings({ background: color })}
                  />
                ))}
              </div>
            </div>
          </section>

          {selectedElement ? (
            <section className={styles.remoteSection}>
              <h3 className={styles.remoteSectionTitle}>Selected Element</h3>
              <div className={styles.remoteField}>
                <label className={styles.remoteLabel}>Label</label>
                <input
                  className={styles.input}
                  value={selectedElement.label}
                  onChange={(event) => updateSelectedElement({ label: event.target.value })}
                />
              </div>
              <div className={styles.remoteField}>
                <label className={styles.remoteLabel}>Content</label>
                <textarea
                  className={styles.input}
                  value={selectedElement.content}
                  onChange={(event) => updateSelectedElement({ content: event.target.value })}
                />
              </div>
              <div className={styles.remoteField}>
                <label className={styles.remoteLabel}>Accent</label>
                <div className={styles.colorRow}>
                  {accentBackgrounds.map((color) => (
                    <button
                      key={color}
                      type="button"
                      className={styles.colorSwatch}
                      style={{ background: color }}
                      onClick={() => updateSelectedElement({ background: color })}
                    />
                  ))}
                </div>
              </div>
              <div className={styles.promptActions}>
                <button type="button" className={styles.secondaryButton} onClick={duplicateSelectedElement}>
                  Duplicate
                </button>
                <button type="button" className={styles.secondaryButton} onClick={removeSelectedElement}>
                  Delete
                </button>
              </div>
            </section>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}
