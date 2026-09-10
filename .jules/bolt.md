## 2025-02-12 - Eliminated O(N log N) Final Sort in Backend Email Fetching

**Learning:** The database query inside `get_emails` (`backend/api/emails.py`) already returns rows sorted chronologically descending (`order_by(Email.date.desc())`). Previously, this array was manually reversed, grouped by thread with a dictionary, and then the dictionary values were sorted again into descending order. Because Python 3.7+ preserves dictionary insertion order, iterating the descending query results and inserting elements into a group dictionary inherently guarantees that the dict's values are strictly ordered by the *newest message in each thread*. This eliminates the need for both the `O(N)` list reversal and the costly `O(N log N)` `sorted()` final step when assembling threads.

**Action:** Whenever iterating pre-sorted array lists from the database to group them into unique threads or items, leverage Python's dictionary insertion order preservation guarantees instead of explicitly appending arrays and sorting them. The first item encountered sets the insertion order, and if the parent array is already sorted descending, the resulting grouped entries are mathematically guaranteed to be correctly ordered.
## 2026-07-11 - O(N) Array Mapping Blocked Main Thread in Kanban Board
**Learning:** When long arrays (like tasks sorted into Kanban columns) are mapped inline directly in the React return function, unrelated parent state changes (e.g., search or filter input) trigger full recalculation of the list and React VDOM reconciliation. This blocks the main thread during simple inputs.
**Action:** Use `useMemo` to wrap expensive multi-column mapping operations that render lists of components, using specific dependencies, preventing rendering bottlenecks when other unrelated state variables are updated.

## 2024-05-24 - Memoizing inline array maps
**Learning:** Inline mapping of arrays inside JSX in large React components causes O(N) recalculation on every render.
**Action:** Wrap inline JSX elements that map over arrays (e.g., lists of tasks) in a `useMemo` hook with specific dependencies.

## 2025-02-12 - Avoided unused setdefault list allocations in grouping loops

**Learning:** `dict.setdefault(key, []).append(value)` evaluates the empty-list default on every iteration, including when the key already exists. In grouping loops, `defaultdict(list)` avoids those transient unused list allocations while preserving insertion order.
**Action:** Use `defaultdict(list)` when missing keys are intentionally initialized with lists. Keep `setdefault` when its eager-default behavior or an ordinary `dict` is part of the required contract, and benchmark before claiming a material end-to-end improvement.
## 2026-07-20 - Set Membership Over Dictionary Truthiness

**Learning:** When using a dictionary purely to track the presence of keys (e.g. `has_sent_message[key] = True`), checking for presence with `.get(key, False)` carries unnecessary semantic and memory overhead. Sets in Python provide a cleaner `key in set_name` syntax for boolean presence checks and slightly reduced memory footprint, while maintaining O(1) time complexity.
**Action:** When tracking unique occurrences or boolean presence of items where the value itself doesn't carry additional information, use a `set` and its `.add()` and `in` operators instead of a `dict` mapping to `True` or `False`.
## 2025-02-12 - Replaced O(N) Array Lookups with O(1) Maps in Loops

**Learning:** When generating derived UI state in `useMemo` that joins separate data arrays (like graph edges referencing node IDs), calling helper functions that use `Array.prototype.find()` for every item creates an `O(M * N)` bottleneck.
**Action:** When a loop needs to repeatedly look up related items from another array by ID, pre-compute an `O(N)` `Map` before the loop and use `map.get()` for `O(1)` lookups instead of inline array `.find()` calls.
## 2024-05-24 - [React Component Memoization]
**Learning:** In React components like `WorkspaceHome`, when layout state or polling changes trigger parent re-renders, expensive child components like `EmailDetail` will also re-render unnecessarily if not memoized.
**Action:** Always consider `React.memo` for heavy child components that rely on stable props (like IDs) when the parent component has frequent unrelated state updates.
