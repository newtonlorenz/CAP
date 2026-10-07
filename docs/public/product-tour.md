# Product tours

The authenticated workspace offers short, optional introductions to its main sections.
Each section tour explains its purpose, key principles, and how to get started.
Section tours have four to six steps.
The eight-step overview introduces licences, certifications, changes, requirements, assessments, evidence, and reports.

The invitation names the current section and shows its step count.
It does not move focus or change the current page.
Select **Start product tour** to begin.
Select **Not now** to dismiss this section's invitation.
Use **Resources → Help → Product tour** to replay the current section on desktop.
Use **Navigation → Help → Product tour** on mobile.
Lists, records, and tabs in the same section share one tour and its saved state.
Changing records or filters does not create another invitation.

Tour steps explain the section without executing actions.
They do not navigate, open editors, create records, upload evidence, submit forms, or change permissions.
Unsaved field values remain intact.
No analytics service receives tour events.
The explanation does not establish regulatory acceptance, certification, or submission success.

## Navigation and accessibility

Visible controls receive a spotlight on desktop and mobile.
Missing or hidden controls use a floating explanation instead.
This also supports empty lists and records that the user cannot access.
Overview navigation targets use floating explanations on mobile.
The mobile drawer closes before the tour starts to prevent competing focus traps.
The desktop breakpoint is 1280 pixels.
The desktop Resources panel expands only when the tour needs its links.
Closing the tour restores the previous panel state.

Use **Back**, **Next**, and **Finish** to move through steps.
Arrow keys also move through steps.
Use **Close product tour** or Escape to dismiss it.
Tab stays within tour controls.
Highlighted application controls cannot receive tour interactions.
Next and Back wait for the spotlight to settle.
Keyboard movement requested during a transition continues after that transition.
Escape remains available throughout.
Closing restores focus to the launch control when available.
Otherwise, focus returns to Resources or the mobile navigation button.
Reduced-motion preferences disable animations and smooth scrolling.

Invitation eligibility is decided at each route or session boundary.
Once shown, the invitation stays in place while fields gain focus, keeping clicks stable.
An editor or dialog active at that boundary defers the invitation until a new boundary.
The Help replay entry remains available.
A tour does not start over an existing edit or confirmation dialog.

Page changes, identity changes, unmounting, and viewport size changes interrupt the tour.
Returning to the interrupted section offers an explicit resume from its last step.
Tours never reopen automatically.
Other sections retain their own completion and dismissal state.

## Persistence and maintenance

State is local to this browser, authenticated user, section tour, and tour version.
It does not sync between devices.
The key is `cap:product-tour:v2:<encoded-user-id>:<encoded-tour-id>`.
Records contain `status` and `step`.
Status is `dismissed`, `completed`, or `interrupted`.
Steps are zero-based indexes within the selected tour.
Version 2 replaces the original four-step introduction; old records do not suppress the expanded tours.
Blocked storage retains each section's state for the current mounted session.
Reloading may offer invitations again when storage is blocked.
Invalid records and out-of-range indexes are ignored.

Maintain definitions and route selection in `frontend/src/components/productTourCatalog.ts`.
Keep matching `data-tour` attributes on page controls and navigation links.
Use one stable identifier for each main section, independent of tabs and record identifiers.
Increment `PRODUCT_TOUR_VERSION` when changes require a new invitation for existing users.
Catalog copy is escaped before Driver.js renders it.
Never insert record or customer content into tour HTML.
Driver.js and its CSS load only after an explicit start.
The dependency uses the npm lockfile and local bundles.

Run focused unit tests with:

```sh
npm --prefix frontend test -- --run src/test/product_tour.test.tsx src/test/section_product_tour.test.tsx src/test/layout_navigation.test.tsx
npm --prefix frontend run test:e2e:onboarding
```

The browser suite uses synthetic API responses and an isolated Vite server.
It does not use a production database.
