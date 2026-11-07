import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { KeyboardSortableList } from "./sortable-grid";

function Harness() {
  const [items, setItems] = useState(["Alpha", "Bravo", "Charlie"]);
  return (
    <KeyboardSortableList
      itemKey={(item) => item}
      items={items}
      labels={{
        drag: "Drag to reorder",
        moveDown: "Move down",
        moveUp: "Move up",
        moved: "Moved to position",
      }}
      onReorder={setItems}
      render={(item) => item}
    />
  );
}

describe("KeyboardSortableList", () => {
  it("supports pointer drag and keyboard-button ordering with stable keys", () => {
    render(<Harness />);
    const handles = screen.getAllByRole("img", { name: "Drag to reorder" });
    const rows = screen.getAllByRole("listitem");
    fireEvent.dragStart(handles[0]!);
    fireEvent.dragOver(rows[2]!);
    fireEvent.drop(rows[2]!);
    expect(screen.getAllByRole("listitem").map((row) => row.textContent)).toEqual([
      expect.stringContaining("Bravo"),
      expect.stringContaining("Charlie"),
      expect.stringContaining("Alpha"),
    ]);

    fireEvent.click(screen.getAllByRole("button", { name: "Move up" })[2]!);
    expect(screen.getAllByRole("listitem")[1]).toHaveTextContent("Alpha");
  });
});
