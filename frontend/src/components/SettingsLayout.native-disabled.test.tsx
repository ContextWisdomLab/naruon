import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const settingsSource = readFileSync(
  resolve(process.cwd(), "src/components/SettingsLayout.tsx"),
  "utf8",
);

function openingButtonTag(marker: string): string {
  const markerIndex = settingsSource.indexOf(marker);
  expect(markerIndex).toBeGreaterThan(-1);

  const buttonStart = settingsSource.lastIndexOf("<button", markerIndex);
  const buttonEnd = settingsSource.indexOf(">", buttonStart);
  expect(buttonStart).toBeGreaterThan(-1);
  expect(buttonEnd).toBeGreaterThan(buttonStart);

  return settingsSource.slice(buttonStart, buttonEnd + 1);
}

describe("SettingsLayout native disabled semantics", () => {
  it("keeps the two repaired buttons on native disabled and aria-busy semantics", () => {
    const accountSaveButton = openingButtonTag("계정 설정 저장");
    expect(accountSaveButton).toContain("disabled={accountSaving || !accountReady}");
    expect(accountSaveButton).toContain("aria-busy={accountSaving}");
    expect(accountSaveButton).not.toContain("aria-disabled=");

    const runnerRotateButton = openingButtonTag("등록 토큰을 회전합니다");
    expect(runnerRotateButton).toContain("disabled={runnerRotating}");
    expect(runnerRotateButton).toContain("aria-busy={runnerRotating}");
    expect(runnerRotateButton).not.toContain("aria-disabled=");
  });
});
