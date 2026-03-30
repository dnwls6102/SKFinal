"use client";

import { useRef } from "react";
import { blockCatalog } from "@/lib/catalog/blocks";
import { useBuilderStore } from "@/store/builder-store";
import type { PageElement } from "@/types/builder";
import styles from "./builder.module.css";

const accentCycle = ["#d9e7f6", "#fee6cf", "#dfead5", "#f9dfe5", "#fffdf8"];

function renderElement(element: PageElement) {
  if (element.type === "image") {
    return (
      <div className={`${styles.elementInner} ${styles.elementImage}`}>
        <strong>{element.content}</strong>
      </div>
    );
  }

  if (element.type === "button") {
    return <div className={`${styles.elementInner} ${styles.elementButton}`}>{element.content}</div>;
  }

  if (element.type === "heading") {
    return <div className={`${styles.elementInner} ${styles.elementHeading}`}>{element.content}</div>;
  }

  return <div className={styles.elementInner}>{element.content}</div>;
}

export function BuilderCanvas() {
  const canvasRef = useRef<HTMLDivElement>(null);
  const project = useBuilderStore((state) => state.project);
  const selectedElementId = useBuilderStore((state) => state.selectedElementId);
  const addElement = useBuilderStore((state) => state.addElement);
  const setSelectedElement = useBuilderStore((state) => state.setSelectedElement);
  const updateElementPosition = useBuilderStore((state) => state.updateElementPosition);
  const updateSelectedElement = useBuilderStore((state) => state.updateSelectedElement);

  const placeElementFromType = (type: string, clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const definition = blockCatalog.find((item) => item.type === type);
    if (!definition) {
      return;
    }

    const rect = canvas.getBoundingClientRect();
    addElement(
      definition,
      Math.max(12, clientX - rect.left - (definition.defaultProps.width / 2)),
      Math.max(12, clientY - rect.top - 20)
    );
  };

  return (
    <div className={styles.canvasWrap}>
      <div
        ref={canvasRef}
        className={styles.canvas}
        style={{
          width: `${project.settings.width}px`,
          minHeight: `${project.settings.minHeight}px`,
          background: project.settings.background
        }}
        onClick={() => setSelectedElement(null)}
        onDragOver={(event) => {
          if (event.dataTransfer.types.includes("application/x-builder-element")) {
            event.preventDefault();
          }
        }}
        onDrop={(event) => {
          const type = event.dataTransfer.getData("application/x-builder-element");
          if (!type) {
            return;
          }

          event.preventDefault();
          placeElementFromType(type, event.clientX, event.clientY);
        }}
      >
        {project.elements.map((element, index) => (
          <div
            key={element.id}
            className={`${styles.element} ${selectedElementId === element.id ? styles.elementSelected : ""}`}
            style={{
              left: `${element.x}px`,
              top: `${element.y}px`,
              width: `${element.width}px`,
              height: `${element.height}px`,
              background: element.background,
              color: element.color,
              borderRadius: `${element.borderRadius}px`,
              fontSize: `${element.fontSize}px`
            }}
            onClick={(event) => {
              event.stopPropagation();
              setSelectedElement(element.id);
            }}
            onDoubleClick={() => {
              const next = accentCycle[(index + 1) % accentCycle.length];
              setSelectedElement(element.id);
              updateSelectedElement({ background: next });
            }}
            onPointerDown={(event) => {
              event.stopPropagation();
              setSelectedElement(element.id);

              const target = event.currentTarget;
              const startX = event.clientX;
              const startY = event.clientY;
              const originX = element.x;
              const originY = element.y;

              const handleMove = (moveEvent: PointerEvent) => {
                const deltaX = moveEvent.clientX - startX;
                const deltaY = moveEvent.clientY - startY;
                updateElementPosition(
                  element.id,
                  Math.max(0, originX + deltaX),
                  Math.max(0, originY + deltaY)
                );
              };

              const handleUp = () => {
                target.releasePointerCapture(event.pointerId);
                window.removeEventListener("pointermove", handleMove);
                window.removeEventListener("pointerup", handleUp);
              };

              target.setPointerCapture(event.pointerId);
              window.addEventListener("pointermove", handleMove);
              window.addEventListener("pointerup", handleUp);
            }}
          >
            {renderElement(element)}
          </div>
        ))}

        <div className={styles.canvasHint}>Drag from the remote or click an element to edit it.</div>
      </div>
    </div>
  );
}
