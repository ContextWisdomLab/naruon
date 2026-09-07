# WebDAV write-confirmation accessibility boundary

Status: **Proposed** until the exact integrated PR head has current frontend/browser evidence and an independent accessibility review.

## Problem

The Data workspace can dispatch an explicit customer WebDAV write after the user selects a server-authoritative workspace document and a write-capable WebDAV source. The confirmation surface therefore changes customer-owned source-of-truth data when confirmed. A visual warning alone is insufficient: keyboard and assistive-technology users must receive the same bounded decision surface, and `aria-modal="true"` must not claim modality while pointer or keyboard interaction with the underlying page remains possible.

A document action also captures the selected repository asset and, for WebDAV materialization, the selected WebDAV source before the request is dispatched. Allowing either selection to change while that action remains pending would let the completion/status UI appear beside a different document or source than the one actually submitted.

## Constraints and decision

Naruon keeps the confirmation as an `alertdialog` because it interrupts an explicit external-write action and requires a binary decision. The interaction contract is:

- `aria-labelledby` and `aria-describedby` identify the warning and consequence;
- `aria-modal="true"` is used only with a full-viewport modal layer that visually obscures and blocks pointer interaction with the underlying page;
- opening moves focus to the non-destructive **취소** action;
- Tab and Shift+Tab remain within the two confirmation actions;
- Escape cancels without dispatching the provider write;
- body scrolling is locked while the confirmation is open;
- cancel and confirmed completion restore focus to the invoking WebDAV write control;
- while any document action is pending, repository-asset and WebDAV-account selection are disabled so the visible selection cannot drift away from the request context; and
- the confirmed provider request remains the existing server-authoritative, conflict-aware WebDAV materialization path rather than a client-side write.

An inline `alertdialog` with `aria-modal="true"` was rejected. WAI-ARIA APG explicitly warns that `aria-modal="true"` is appropriate only when application code prevents interaction outside the dialog and the visual presentation also obscures outside content. A non-modal inline confirmation was also rejected because this action mutates a customer-owned external source and the existing product contract intentionally requires an interruptive confirmation.

The implementation follows the same repository accessibility shape already used by `frontend/src/components/SourceDrawer.tsx`: visible modal layer, focus entry, keyboard containment, Escape handling, body scroll lock, and focus restoration. It does not introduce a new design-system dependency or claim that a shadcn/ui source component is being used.

## Test and change traceability

- `190fb909627074d15b03f750c72fec556510496c` introduced a focused component regression before the focus/keyboard repair.
- `364895b7a246f35e0faacba163760315e2f78acd` restored focus entry, cyclic Tab/Shift+Tab, Escape cancellation, and invoker focus restoration while preserving the newer per-action busy-state changes.
- `2e6881395e204083041aa92122a7df233d8b3edb` removed unrelated `.jules/codeql.md` and product-gap receipt changes from this product UI writer.
- `e29f7e58ff1dbc4cb35c20d053016090de9a26ea` aligned the focused fixture with the typed WebDAV/account and repository-asset contracts.
- `dfd8ec72a3f23e257b42853fbff4eb8d03350a7c` strengthened the regression so `aria-modal` must correspond to a full-viewport interaction boundary and body scroll lock.
- `43cf974a50d69f3109893f73a53a97d40dd1d70f` implemented the full-viewport modal layer and scroll lock while retaining the focus contract.
- `78c690de92e2767834c6fac99e331c263410063e` added the source-order regression that requires WebDAV-account and repository-asset selection to remain frozen during a pending document action.
- `517c8e7ccd6081250ebbceba82dc1dac2fb533aa` disabled WebDAV-account selection and made repository-asset mouse/keyboard selection inert with `aria-disabled` while the action is pending.

These commits establish source-order RED→repair provenance. They are not, by themselves, exact-head GREEN. Promotion from Proposed requires current-head frontend/component and browser/E2E checks without warning-class failures, plus the normal repository review gates.

## References

World Wide Web Consortium, Web Accessibility Initiative. (n.d.). *Alert and message dialogs pattern*. WAI-ARIA Authoring Practices Guide. https://www.w3.org/WAI/ARIA/apg/patterns/alertdialog/

World Wide Web Consortium, Web Accessibility Initiative. (n.d.). *Dialog (modal) pattern*. WAI-ARIA Authoring Practices Guide. https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
