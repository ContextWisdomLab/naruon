## 2024-06-06 - Replacing UI dev notes with user-facing text
**Learning:** Legacy UI components might contain placeholder or dev-centric descriptive text (e.g., "legacy AuditLog는 직접 노출하지 않습니다.") that isn't ideal for end-users.
**Action:** When finding UI elements describing internal technical details, replace them with clear, end-user descriptions explaining the feature's value in a localized and user-friendly manner, then verify via visual playwright inspection.

## 2026-06-08 - Add loading state to Search Submit Button
**Learning:** The search submit button lacked a disabled and visual loading state during query execution, which can lead to accidental duplicate submissions and poor user feedback. Using the existing loading state, disabling the button with appropriate styling `disabled:cursor-wait disabled:opacity-60`, and changing the copy to "검색 중" resolves this.
**Action:** Always ensure async operations, like search or submit buttons, have explicit loading feedback and are disabled to prevent duplicate actions.

## 2026-06-08 - Accessible Search Inputs Across Layouts
**Learning:** Search inputs placed in complex dashboard layouts frequently miss explicitly associated labels and IDs, relying only on placeholders or visual icons, which creates barriers for screen reader users navigating the page landmarks.
**Action:** Always provide a visually hidden `<label>` explicitly tied to the input via `htmlFor` and `id`, and ensure any adjacent decorative search icons have `aria-hidden="true"`.

## 2026-06-08 - Accessible Loading States for Buttons
**Learning:** The native HTML `disabled` attribute inherently communicates the disabled state to screen readers and removes elements from the tab order. Adding `aria-disabled="true"` to a `disabled` button is redundant and can be flagged by accessibility linters. However, adding `aria-busy="true"` during an async operation correctly communicates to screen readers that the element is actively updating.
**Action:** When adding accessible loading states to buttons, use `disabled={isLoading}` for state, add `aria-busy={isLoading}` for context, but avoid redundant `aria-disabled={isLoading}`.

## 2024-06-04 - Semantic Buttons for Task Interactions
**Learning:** Interactive areas that trigger actions (like opening a task detail view or navigating to a source) should be semantic `<button>` elements rather than `<div>`s with `onClick` handlers. `div`s lack native keyboard accessibility, focus rings, and proper screen reader roles. Also, `aria-label`s should be context-aware (e.g., "접수 더보기" instead of just "더보기").
**Action:** When creating new components that function as clickable cards or icon triggers, always wrap them in `<button type="button">` and ensure they have `focus-visible` styles and contextually descriptive `aria-label`s.

## 2024-06-06 - Always Include Focus States for Custom Buttons
**Learning:** Custom UI buttons without explicitly defined focus styles become invisible during keyboard navigation. This fundamentally breaks keyboard accessibility, leaving power users and screen reader users unable to track their current position on the page. In this application, several action and filter buttons lacked proper focus indicators despite having hover states.
**Action:** Whenever creating or modifying custom interactive elements (like `<button>` or `<a>`), unconditionally add standard focus styles, such as `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40`.

## 2026-06-11 - Adding Repository Badges and Communication Guidelines
**Learning:** Organizing a repository with Issue/PR templates, CI badges, and a Code of Conduct creates an immediate impression of professionalism and hygiene, saving developers time on repetitive questions.
**Action:** When setting up a new repository or performing repository hygiene, always ensure a base set of standard templates and CI badges are included.

## 2024-06-12 - Adding a11y Roles to InsightCard Status States
**Learning:** Generic wrapper components like `InsightCard` which dynamically load and present data often conditionally render a generic loader or error state. Screen readers may ignore these visual cues unless they are accompanied by proper semantic roles, such as `role="status"` and `aria-live="polite"` for loading spinners, and `role="alert"` for error messages. Also adding `aria-hidden="true"` to visual icons within these states reduces noise.
**Action:** When creating reusable data-fetching card components, always annotate loading and error state container elements with the appropriate ARIA roles and live regions, and hide purely decorative elements.

## 2026-06-13 - Use type=text for Custom Search Inputs
**Learning:** When implementing a custom clear button for search inputs, using `type="search"` causes WebKit browsers to display a native clear button, resulting in double buttons. While CSS `::-webkit-search-cancel-button` tricks exist, they can be unreliable across environments.
**Action:** Use `<input type="text" inputMode="search" role="searchbox">` only for legacy cases where the native WebKit clear control cannot be hidden; current components should follow the `type="search"` plus `[&::-webkit-search-cancel-button]:hidden` rule below.

## 2025-02-05 - Search clear action keyboard focus flow
**Learning:** When users click a "clear search" icon button to empty an input field, screen readers and keyboard navigation can lose their place in the DOM structure.
**Action:** Always capture a `useRef` to the `<Input>` and explicitly call `ref.current?.focus()` inside the clear button's `onClick` handler to preserve interaction flow.

## 2025-02-28 - Add Loader2 spinner to async buttons in SettingsLayout.tsx
**Learning:** Providing explicit visual feedback, such as a spinning loader, during asynchronous save operations prevents users from wondering if their click registered and improves perceived performance.
**Action:** Always map loading states such as `isSaving` or `isLoading` to explicit UI indicators like the `Loader2` icon with `animate-spin` inside submit buttons, rather than only changing button text or disabling the button.

## 2026-06-16 - Internal tool form accessibility and visual feedback
**Learning:** Internal tool forms can miss basic accessibility attributes like stable IDs, linked labels, and clear async feedback on submit buttons. Without those details, screen readers lose form context and users get weak confirmation during long-running actions.
**Action:** Verify internal form inputs use explicit `label htmlFor`/`id` pairs, decorative icons are `aria-hidden`, and async buttons expose disabled loading states with visible spinner feedback.

## 2026-06-19 - Global search clear button without native WebKit controls
**Learning:** Header-level global search should use the same custom clear-button pattern as the Search page. The `type="text"` + `inputMode="search"` + `role="searchbox"` combination is a legacy fallback only; current components follow the canonical `type="search"` plus `[&::-webkit-search-cancel-button]:hidden` rule below.
**Action:** Keep custom clear buttons in the same wrapper as the search input, label the clear action as `검색어 지우기`, and refocus the input after clearing.
## 2026-06-21 - Accessible Dynamic Empty and Error States
**Learning:** For dynamic, client-side rendered UI components (like graph visualizations or data panels), rendering an empty state or error state message in a standard `div` will not be announced by screen readers when the state suddenly transitions (e.g., from loading to empty).
**Action:** When creating or modifying dynamic empty, error, or loading states that update asynchronously, ensure their container has `role="status"` (or `role="alert"` for errors) and `aria-live="polite"` so screen readers are actively notified of the content change without aggressive interruption.
## 2026-06-21 - Mocking new Lucide icons in tests
**Learning:** Adding a new icon from `lucide-react` (like `Loader2`) to a component without updating the corresponding test file's `vi.mock("lucide-react", ...)` block causes Vitest to throw a "No export is defined on the lucide-react mock" error.
**Action:** When adding new `lucide-react` icons, always grep for `vi.mock("lucide-react"` in the `frontend/src/` directory to find and update the relevant test files.

## 2024-05-24 - Add `aria-busy` to async operation buttons
**Learning:** Action buttons triggering asynchronous network operations need an `aria-busy` attribute, alongside `disabled` state and visual indicators, to correctly communicate their loading state to screen reader users.
**Action:** Add `aria-busy={isLoading}` to action buttons alongside existing spinner and disabled states for network interactions.
## 2024-05-24 - Refresh button loading states
**Learning:** Adding explicit visual indicators (like `animate-spin`) and `aria-busy` to buttons alongside `disabled` states prevents multiple clicks and effectively communicates asynchronous loading to screen readers.
**Action:** When creating action buttons for async operations like '새로고침' (Refresh), always include `disabled={loading}`, `aria-busy={loading}`, adjust opacity (`disabled:opacity-60`), change cursor (`disabled:cursor-not-allowed`), spin icons, and update text to '새로고침 중'.
## 2024-05-17 - Update UI Terminology Mapping
**Learning:** Blind, global string replacement (regex) for translating or standardizing Korean UI terms can lead to semantical breaks. For example, blindly replacing "할 일" to "실행 항목" breaks other valid Korean words containing "할 일" such as "표시할 일정" (changing it to "표시실행 항목정"). Similarly, replacing "검색" with "맥락 검색" indiscriminately can lead to redundant strings like "맥락 맥락 검색".
**Action:** When updating localization strings or terminology across a large codebase, apply context-aware parsing or careful target-word bound replacements rather than naive global string matching. Always manually verify the `git diff` for readability and semantical correctness after applying bulk string manipulations.
## 2026-06-20 - Use semantic `type="search"` with custom clear buttons
**Learning:** Using `type="search"` on input fields improves mobile UX by rendering a semantic search keyboard (with a "Search" submit button instead of "Go/Enter"). However, when adding a custom clear button ('X') using UI components or Tailwind CSS, the native webkit clear button overlaps with it.
**Action:** When implementing search fields, always use `type="search"` instead of `type="text"` to get the semantic keyboard benefits. To prevent visual overlaps with custom clear icons, add the `[&::-webkit-search-cancel-button]:hidden` Tailwind utility class to hide the native webkit clear button.
## 2024-05-24 - Ensure aria-busy accompanies disabled for async UI buttons
**Learning:** Action buttons triggering asynchronous network operations that already implement `disabled={loading}` and visual spinners MUST also include an `aria-busy={loading}` attribute to correctly communicate the active loading state to screen reader users without requiring focus shifts.
**Action:** When adding or auditing buttons for async operations like '동기화 중', '전송 중', or '검색 중', ensure `aria-busy={loadingVariable}` is explicitly added alongside existing spinner and disabled states.
## 2026-06-25 - Explicit Loading Feedback for Intent Generation
**Learning:** In deeply nested data-action layouts (like DataLayout's document and thread intent generation), missing explicit loading spinners and text changes (e.g., from "실행" to "처리 중") leaves users guessing if the button click registered. `disabled` alone is insufficient feedback for intent-checking actions which often take several seconds.
**Action:** When adding asynchronous intent check actions (like WebDAV or thread validations), always combine `disabled={isLoading}`, `aria-busy={isLoading}`, a `Loader2` spinner, and a dynamic text label (e.g. `isLoading ? '점검 중' : '점검'`) to give immediate, unambiguous feedback.
## 2026-06-25 - Use semantic type="search" with custom clear buttons
**Learning:** Using `type="search"` on input fields improves mobile UX by rendering a semantic search keyboard (with a "Search" submit button instead of "Go/Enter"). However, when adding a custom clear button ('X') using UI components or Tailwind CSS, the native webkit clear button overlaps with it.
**Action:** When implementing search fields, always use `type="search"` instead of `type="text"` to get the semantic keyboard benefits. To prevent visual overlaps with custom clear icons, add the `[&::-webkit-search-cancel-button]:hidden` Tailwind utility class to hide the native webkit clear button.
## 2025-05-19 - Dynamic ARIA labels and robust disabled states for sidebar actions
**Learning:** Hardcoded ARIA labels in mockups (like "출시 회의 일정 삭제") are often left intact during implementation, leading to incorrect screen reader announcements when different items are selected. In addition, action buttons that depend on selection state often lack correct visual and functional disabled states.
**Action:** When implementing detail views or sidebars, always replace hardcoded mockup ARIA labels with dynamic data (e.g. `${event.title} 삭제`), and ensure action buttons are explicitly disabled (both functionally via `disabled` and visually via `opacity-50 cursor-not-allowed`) when their prerequisites (like a selected item or specific properties like location) are unmet.
