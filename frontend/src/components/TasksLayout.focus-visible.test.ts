import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const tasksLayoutSource = readFileSync(
  new URL("./TasksLayout.tsx", import.meta.url),
  "utf8",
);

function kanbanTaskButtonOpeningTag(): string {
  const mapAnchor = "tasksByStatus[col.id].map((task)";
  const mapIndex = tasksLayoutSource.indexOf(mapAnchor);
  expect(mapIndex).toBeGreaterThan(-1);

  const buttonIndex = tasksLayoutSource.indexOf("<button", mapIndex);
  const classNamePrefix = 'className="';
  const classNameIndex = tasksLayoutSource.indexOf(classNamePrefix, buttonIndex);
  const classNameEnd = tasksLayoutSource.indexOf(
    '"',
    classNameIndex + classNamePrefix.length,
  );
  const openingTagEnd = tasksLayoutSource.indexOf(">", classNameEnd);

  expect(buttonIndex).toBeGreaterThan(mapIndex);
  expect(classNameIndex).toBeGreaterThan(buttonIndex);
  expect(classNameEnd).toBeGreaterThan(classNameIndex);
  expect(openingTagEnd).toBeGreaterThan(classNameEnd);
  return tasksLayoutSource.slice(buttonIndex, openingTagEnd);
}

describe("TasksLayout Kanban keyboard-focus contract", () => {
  it("keeps a keyboard-only visible focus indicator on each task card", () => {
    const openingTag = kanbanTaskButtonOpeningTag();

    expect(openingTag).toContain("focus-visible:outline-none");
    expect(openingTag).toContain("focus-visible:ring-2");
    expect(openingTag).toContain("focus-visible:ring-ring/40");
  });
});
