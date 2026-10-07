# Echo window controls

Approved: use the Echo arcs from the context preview throughout Lumen, with
symbols at 70% of the preview size and controls on the right, including setup.

- Use one native Aurorae decoration for the assistant, Files, tools, settings and
  wizard; keep KWin's native window actions, tooltips and window capabilities.
- Minimize, maximize/restore, close in that order. Dialogs keep only supported
  actions. Scale the 32 × 28 preview glyph viewport to 22.4 × 19.6 logical pixels;
  retain a 32 × 32 native mouse target. Respect display scaling.
- Support all four Lumen palettes, active/inactive/hover/pressed states. The close
  action becomes warm on hover. No continuous animation or rendering dependency.
- Install under new Echo identities so old cached artwork and customized previous
  packages survive. Updates migrate only a selected legacy Lumen decoration,
  backing up its theme and button arrangement. Other desktop preferences survive.
- Verify resource generation, native SVG rendering, layout writes, rollback,
  repeat updates and untouched non-Lumen decorations; build the Arch package.
