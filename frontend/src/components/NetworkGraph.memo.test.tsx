/* @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";

vi.mock("vis-network", () => ({
  Network: vi.fn(),
}));

import NetworkGraph from "./NetworkGraph";

describe("NetworkGraph memo boundary", () => {
  it("exports the zero-prop graph as a React memo component", () => {
    const memoComponent = NetworkGraph as unknown as { $$typeof?: symbol };

    expect(memoComponent.$$typeof).toBe(Symbol.for("react.memo"));
  });
});
