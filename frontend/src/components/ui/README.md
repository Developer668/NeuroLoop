# Neuro AI components

The project already uses TypeScript and the App Router. Tailwind 4, its PostCSS plugin, and tw-animate-css are installed. `components.json` configures shadcn aliases; `@/components/ui` resolves to `src/components/ui`, matching this project's src layout. No duplicate root components folder is needed.

`app/utilities.css` imports Tailwind theme and utilities without Preflight so existing workspace styling remains intact. The prompt uses scoped CSS and existing workspace color tokens. `lib/utils.ts` provides the standard cn helper.

`ai-chat-input.tsx` implements the supplied expanding prompt layout with the actual MiniMax/Ideogram models, aspect ratios, brand input, and unrestricted reference attachments. Speech recognition is browser-dependent and reports errors instead of producing simulated text. Local command functionality is preserved in `local-command-input.tsx`.

`loading-state.tsx` supplies Drive, Dots, and Orbit patterns with elapsed time. Its animation rules live in `app/neuro.css`, including reduced-motion support. The creative request's busy state controls the loader. `loading-state-demo.tsx` previews all three variants.
