# Supplied UI component integration

Reusable components live in `frontend/src/components/ui`; `@/components/ui` resolves there through the existing TypeScript alias. Global styles live in `frontend/src/app`. This directory keeps imported primitives separate from feature pages; it is an organization convention, not a React requirement.

- `background-paths.tsx`: the supplied two sets of 36 SVG paths are mounted inside the existing landing footer. Deterministic CSS timing avoids random server/client output. Animation pauses outside the visible footer and respects reduced motion. The existing compact footer content is retained instead of adding a second full-screen demo and an inert button.
- `loading-state.tsx`: Drive, Dots and Orbit patterns, shimmer and a real elapsed clock. Neuro mounts it only while the actual command request is pending. The timer uses elapsed time rather than assuming interval callbacks are punctual; it is hidden from live announcements.
- `ai-chat-input.tsx`: the supplied rounded, expanding composer design adapted to controlled draft state and the real local command endpoint. Enter submits, Shift+Enter adds a line, composition input is respected, and duplicate requests are guarded. Commands replace disconnected model/effort controls. Simulated speech and fake responses are omitted. Failed requests preserve the draft.

The project already supports TypeScript and Motion (`motion/react`). It uses authored CSS rather than Tailwind. These integrated components use that existing style system and need no new dependencies or context providers. There are no stock-image requirements in these components.

For future literal shadcn/Tailwind components, configure Tailwind through its Next.js installation guide, then run `npx shadcn@latest init` from `frontend`, setting the components alias to `@/components` and utilities to `@/lib/utils`. Review global reset/token changes before applying them to this existing UI. Install only the dependencies actually imported by an adopted component; the footer adaptation does not import the sample shadcn Button.
