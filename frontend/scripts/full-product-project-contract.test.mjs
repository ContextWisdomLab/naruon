/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { installRoutes } from "./full-product-ui-smoke.mjs";
import { ProjectsLayout } from "../src/components/ProjectsLayout";

vi.mock("next/link", () => ({
  default: ({ children, ...props }) => React.createElement("a", props, children),
}));

let renderRoot;
let renderContainer;

afterEach(async () => {
  if (renderRoot) await act(async () => renderRoot.unmount());
  renderRoot = undefined;
  renderContainer?.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function registeredResponse(endpointPath) {
  const routeHandlers = new Map();
  await installRoutes({ route: async (routePattern, routeHandler) => {
    routeHandlers.set(routePattern, routeHandler);
  } });
  let responseBody;
  const selectedHandler = routeHandlers.get(endpointPath === "/auth/session" ? "**/auth/session" : "**/api/**");
  await selectedHandler({
    request: () => ({ url: () => `http://127.0.0.1:3001${endpointPath}`, method: () => "GET" }),
    fulfill: async (responseValue) => { responseBody = JSON.parse(responseValue.body); },
  });
  return responseBody;
}

it("declares the authenticated session contract explicitly", async () => {
  expect(await registeredResponse("/auth/session")).toMatchObject({
    authenticated: true, claims: { userId: "smoke-user" },
  });
});

it("supplies creation timestamps for every returned task", async () => {
  const taskRows = await registeredResponse("/api/tasks");
  expect(taskRows).toHaveLength(3);
  for (const taskRow of taskRows) expect(taskRow.created_at).toEqual(expect.any(String));
});

it("returns a candidate collection instead of generic placeholder success", async () => {
  expect(await registeredResponse("/api/projects/candidates")).toEqual({ candidates: [] });
});

it("renders actual project readiness from the registered unit responses", async () => {
  vi.stubGlobal("fetch", vi.fn(async (requestPath) => ({
    ok: true, status: 200,
    json: async () => registeredResponse(String(requestPath)),
  })));
  renderContainer = document.createElement("div");
  document.body.appendChild(renderContainer);
  renderRoot = createRoot(renderContainer);
  await act(async () => renderRoot.render(React.createElement(ProjectsLayout)));
  expect(renderContainer.textContent).not.toContain("프로젝트 근거를 불러오지 못했습니다");
  expect(Array.from(renderContainer.querySelectorAll("a")).some((linkElement) =>
    linkElement.textContent === "관련 문서/메일 연결",
  )).toBe(true);
});
