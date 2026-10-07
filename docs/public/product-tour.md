# Product tour

The authenticated workspace offers an optional four-step Driver.js tour.
The invitation does not move focus or change the current page.
Its visibility is decided at each route or session boundary.
Once shown, it stays in place while fields gain focus, keeping clicks stable.
An editor or dialog already active at that boundary defers the invitation until
a new boundary; the Help replay entry remains available.
Select **Start product tour** to begin.
Select **Not now** to dismiss the invitation.
On desktop, use **Resources → Help → Product tour** to replay it.
On mobile, use **Navigation → Help → Product tour**.

The tour explains requirements, assessments, evidence, and reports.
It does not create records, upload evidence, submit forms, or change permissions.
No analytics service receives tour events.

## Navigation and accessibility

At desktop widths, steps highlight links in the Resources panel.
The panel stays open while tour controls have focus.
Closing the tour restores the previous panel state.
The desktop breakpoint is 1280 pixels.
Mobile steps use floating popovers with navigation paths.
The mobile drawer closes before the tour starts.
This prevents competing focus traps.

Use **Back**, **Next**, and **Finish** to move through the tour.
Arrow keys also move through steps.
Use **Close product tour** or Escape to dismiss it.
Tab stays within the tour controls.
Closing restores focus to the launch control when available.
Otherwise, focus returns to Resources or the mobile navigation button.
Reduced-motion preferences disable tour animations and smooth scrolling.

Missing navigation targets use floating popovers.
Targets are resolved when each step opens, including after navigation renders.
No synthetic requirement or evidence record is needed.
Page changes, identity changes, unmounting, and viewport width changes interrupt the tour.
Interrupted tours offer an explicit resume from the last step.
They never reopen automatically.

## Persistence and maintenance

State is local to this browser and authenticated user.
It does not sync between devices.
The key is `cap:product-tour:v1:<encoded-user-id>`.
Records contain `status` and `step`.
Status is `dismissed`, `completed`, or `interrupted`.
Steps are zero-based indexes from 0 to 3.
Blocked storage retains state for the current mounted session.
Reloading may offer the invitation again when storage is blocked.
Invalid records are ignored.

Maintain step copy and selectors in `frontend/src/components/useProductTour.ts`.
Keep matching `data-tour` attributes on navigation links in `Layout.tsx`.
Increment `PRODUCT_TOUR_VERSION` when existing users need a new invitation.
Driver.js and its CSS load only after an explicit start.
The dependency uses the npm lockfile and local bundles.

Run focused unit tests with:

```sh
npm --prefix frontend test -- --run src/test/product_tour.test.tsx src/test/layout_navigation.test.tsx
npm --prefix frontend run test:e2e:onboarding
```

The browser suite uses synthetic API responses and an isolated Vite server.
It does not use a production database.
