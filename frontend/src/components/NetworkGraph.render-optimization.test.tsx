// @vitest-environment jsdom
import React, { useState, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let renderCount = 0;

// Mock the NetworkGraph component to track its renders.
vi.mock('./NetworkGraph', async () => {
  const React = await vi.importActual('react');
  const MockedNetworkGraph = () => {
    renderCount++;
    return <div data-testid="network-graph-mock">NetworkGraph Mock</div>;
  };
  return {
    default: React.memo(MockedNetworkGraph),
  };
});

import NetworkGraph from './NetworkGraph';

describe('NetworkGraph React.memo optimization', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    renderCount = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    if (container.parentNode) {
      container.parentNode.removeChild(container);
    }
  });

  it('does not re-render when parent state changes unrelated to its props', async () => {
    const ParentComponent = () => {
      const [count, setCount] = useState(0);
      return (
        <div>
          <button data-testid="parent-button" onClick={() => setCount(c => c + 1)}>
            Increment {count}
          </button>
          <NetworkGraph />
        </div>
      );
    };

    await act(async () => {
      root.render(<ParentComponent />);
    });

    // Initial render
    expect(renderCount).toBe(1);

    // Trigger parent re-render
    const button = container.querySelector('[data-testid="parent-button"]') as HTMLButtonElement;
    await act(async () => {
      button.click();
    });

    // NetworkGraph should NOT re-render because it has no props and is wrapped in React.memo
    expect(renderCount).toBe(1);
    expect(button.textContent).toBe('Increment 1');
  });
});
