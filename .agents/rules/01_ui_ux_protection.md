# UI/UX Protection Rule

## Core Rule: NO UI/UX REDESIGN

Development agents must NEVER redesign, overhaul, or restyle the user interface of CodeGuard (`apps/web/`).

## Specific Prohibitions

1. **Colors and Themes**: Do not change color palettes, dark mode implementations, or Tailwind CSS theme definitions.
2. **Layouts and Grid**: Do not modify dashboard layouts, grid alignments, page containers, or responsive breakpoints.
3. **Navigation**: Do not restructure navigation bars, sidebars, routing hierarchies, or breadcrumbs.
4. **Component Hierarchy**: Do not replace custom components with third-party design systems or alternative component libraries unless explicitly instructed by the user.
5. **Visual Elements**: Do not alter icons, typography, or animation timing.

## Allowed Actions

The Frontend Agent is strictly limited to:
- Wiring real API endpoints to replace static or disconnected state.
- Fixing functional runtime bugs (e.g. unhandled null checks, broken event handlers).
- Enhancing error handling and loading indicators within existing UI containers.
