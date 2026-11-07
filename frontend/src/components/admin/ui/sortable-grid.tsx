"use client";

import { ArrowDown, ArrowUp, DotsSixVertical } from "@phosphor-icons/react";
import { type ReactNode, useState } from "react";

export function KeyboardSortableList<T>({
  items,
  itemKey,
  render,
  onReorder,
  labels,
}: {
  items: T[];
  itemKey: (item: T) => string;
  render: (item: T, index: number) => ReactNode;
  onReorder: (items: T[]) => void;
  labels: { moveUp: string; moveDown: string; drag?: string; moved?: string };
}) {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState("");

  function commit(next: T[], position: number) {
    onReorder(next);
    setAnnouncement(labels.moved ? `${labels.moved} ${position + 1}` : "");
  }

  function move(index: number, offset: -1 | 1) {
    const target = index + offset;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target]!, next[index]!];
    commit(next, target);
  }

  function drop(target: number) {
    if (draggedIndex === null || draggedIndex === target) return;
    const next = [...items];
    const [moved] = next.splice(draggedIndex, 1);
    if (!moved) return;
    next.splice(target, 0, moved);
    commit(next, target);
    setDraggedIndex(null);
  }
  return (
    <>
      <span aria-live="polite" className="sr-only">
        {announcement}
      </span>
      <ol className="grid gap-3">
        {items.map((item, index) => (
          <li
            key={itemKey(item)}
            className="flex items-center gap-3 rounded-2xl border border-brand-purple/12 bg-white p-3"
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => drop(index)}
          >
            <span
              aria-label={labels.drag ?? labels.moveDown}
              className="grid size-11 shrink-0 cursor-grab place-items-center rounded-xl text-muted active:cursor-grabbing"
              draggable
              onDragEnd={() => setDraggedIndex(null)}
              onDragStart={() => setDraggedIndex(index)}
              role="img"
            >
              <DotsSixVertical aria-hidden size={22} weight="bold" />
            </span>
            <div className="min-w-0 flex-1">{render(item, index)}</div>
            <div className="grid shrink-0 grid-cols-2 gap-1 sm:grid-cols-1">
              <button
                aria-label={labels.moveUp}
                className="grid size-11 place-items-center rounded-xl border border-brand-purple/15 disabled:opacity-35"
                disabled={index === 0}
                onClick={() => move(index, -1)}
                type="button"
              >
                <ArrowUp aria-hidden size={18} />
              </button>
              <button
                aria-label={labels.moveDown}
                className="grid size-11 place-items-center rounded-xl border border-brand-purple/15 disabled:opacity-35"
                disabled={index === items.length - 1}
                onClick={() => move(index, 1)}
                type="button"
              >
                <ArrowDown aria-hidden size={18} />
              </button>
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}
