import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const settingsSource = readFileSync(
  fileURLToPath(new URL("./SettingsLayout.tsx", import.meta.url)),
  "utf8",
);

function openingButtonTag(marker: string): string {
  const markerIndex = settingsSource.indexOf(marker);
  expect(markerIndex).toBeGreaterThan(-1);

  const buttonStart = settingsSource.lastIndexOf("<button", markerIndex);
  const buttonEnd = settingsSource.indexOf(">", markerIndex);
  expect(buttonStart).toBeGreaterThan(-1);
  expect(buttonEnd).toBeGreaterThan(markerIndex);

  return settingsSource.slice(buttonStart, buttonEnd + 1);
}

describe("SettingsLayout native disabled semantics", () => {
  it("keeps the account save button natively disabled and busy without redundant aria-disabled", () => {
    const buttonTag = openingButtonTag("계정 설정 저장");

    expect(buttonTag).toContain("disabled={accountSaving || !accountReady}");
    expect(buttonTag).toContain("aria-busy={accountSaving}");
    expect(buttonTag).not.toContain("aria-disabled=");
  });

  it("keeps the runner token rotate button natively disabled and busy without redundant aria-disabled", () => {
    const buttonTag = openingButtonTag("등록 토큰을 회전합니다");

    expect(buttonTag).toContain("disabled={runnerRotating}");
    expect(buttonTag).toContain("aria-busy={runnerRotating}");
    expect(buttonTag).not.toContain("aria-disabled=");
  });
});
