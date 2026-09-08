# NetworkGraph constant-time lookup plan

1. Pre-compute `edgeMap` and `nodeInstanceMap` with `useMemo`, and keep the existing `nodeMap` as the authoritative node-label lookup for rendered selections.
   - `selectEdge` uses `edgeMap.get(String(edgeId))`.
   - `selectNode` uses `nodeMap.get(String(nodeId))` with the node identifier as the no-entry fallback.
   - `selectGraphNode` uses `nodeMap.get(String(node.id))` with the node identifier as the no-entry fallback.
   - `handleRelationshipOptionChange` uses `edgeMap.get(value)`.
   - `handleNodeOptionChange` uses `nodeInstanceMap.get(value)`.
   - Selection handlers must not fall back to `Array.prototype.find()` or `findNodeLabel()` scans.
   - `edgeMap` and `nodeInstanceMap` are first-wins, matching `nodeMap` and the previous `.find()` path. Last-wins `new Map(items.map(...))` construction is rejected.

2. Verify the exact branch head from `frontend/` with these commands:

   ```bash
   pnpm test -- src/components/NetworkGraph.test.tsx src/components/NetworkGraph.map-lookup.test.ts
   pnpm exec eslint src/components/NetworkGraph.tsx src/components/NetworkGraph.test.tsx src/components/NetworkGraph.map-lookup.test.ts
   pnpm typecheck
   pnpm build
   ```

3. Keep the pull request open until the unchanged exact head has terminal-success required checks, all addressed review threads are resolved, and protected-branch review requirements are satisfied without bypass.
