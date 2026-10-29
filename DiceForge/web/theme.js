// The look of what DiceForge draws in and at nodes (the panels of LoRA Stack, Dice Grid, Random Image, Danbooru Tag Enhancer and XY Plot, the
// ⋯ menus, the autocomplete), taken from ComfyUI's own palette variables, so it follows the palette the user picks (dark, light or their
// own) as the core widgets do, with nothing to redraw. Panels get the class df-ui, popups df-ui df-pop.
//
// Classic nodes take the palette's base colors (--comfy-input-bg and --input-text, as the core text fields do) and LiteGraph's widget
// metrics (20 px, round ends, an outline); Nodes 2.0 nodes (inside .lg-node) take the Vue widgets' colors and metrics (24 px, 6 px corners,
// no outline). Colored text (errors, ✓, the random range, links) is a hue mixed with the text color: lighter on a dark palette, darker on a
// light one, readable on both. Pictures keep their own dark overlays, which don't depend on the palette.
const THEME = `
.df-ui{--df-fg:var(--input-text,#ddd);--df-muted:var(--descrip-text,#999);
--df-surface:color-mix(in srgb,var(--df-fg) 5%,transparent);--df-line:color-mix(in srgb,var(--df-fg) 18%,transparent);
--df-field:var(--comfy-input-bg,#222);--df-field-hover:color-mix(in srgb,var(--df-field) 85%,var(--df-fg));--df-field-line:var(--border-color,#4e4e4e);
--df-field-fg:var(--input-text,#ddd);--df-focus:var(--descrip-text,#999);
--df-primary:var(--primary-background,#0b8ce9);--df-on-primary:#fff;--df-selected:color-mix(in srgb,var(--df-primary) 25%,transparent);
--df-track:color-mix(in srgb,var(--df-fg) 30%,transparent);--df-knob:var(--comfy-menu-bg,#171718);
--df-error:color-mix(in srgb,#e53935 60%,var(--df-fg));--df-error-line:var(--error-text,#f44);
--df-warn:color-mix(in srgb,#fb8c00 60%,var(--df-fg));--df-warn-line:var(--warning-background,#fd9903);
--df-ok:color-mix(in srgb,#43a047 60%,var(--df-fg));--df-link:color-mix(in srgb,#1e88e5 60%,var(--df-fg));
--df-h:20px;--df-r-field:10px;--df-r-card:8px;
font:12px/16px var(--font-inter,Inter,sans-serif);color:var(--df-fg)}
.lg-node .df-ui{--df-fg:var(--component-node-foreground,#fff);--df-muted:var(--component-node-foreground-secondary,#8a8a8a);
--df-field:var(--component-node-widget-background,#313235);--df-field-hover:var(--component-node-widget-background-hovered,#494a50);
--df-field-line:transparent;--df-field-fg:var(--component-node-foreground,#fff);--df-focus:var(--component-node-widget-background-highlighted,#8a8a8a);
--df-track:var(--border-default,#494a50);--df-knob:var(--base-background,#171718);--df-h:24px;--df-r-field:var(--radius-md,6px);--df-r-card:var(--radius-lg,8px)}
.df-ui :is(button,input[type=number],input[type=text]){box-sizing:border-box;height:var(--df-h);border-radius:var(--df-r-field);background:var(--df-field);
color:var(--df-field-fg);border:1px solid var(--df-field-line);font:inherit;padding:0 8px;margin:0}
.df-ui button{cursor:pointer}.df-ui button:hover:not(:disabled){background:var(--df-field-hover)}.df-ui button:disabled{opacity:.5;cursor:default}
.df-ui :is(button,input):focus-visible{outline:1px solid var(--df-focus);outline-offset:0}
.df-ui button.primary{background:var(--df-primary);color:var(--df-on-primary);border-color:transparent}
.df-ui button.primary:hover:not(:disabled){background:color-mix(in srgb,var(--df-primary) 85%,var(--df-fg))}
.df-ui button.icon{width:var(--df-h);padding:0;background:transparent;border-color:transparent;color:var(--df-muted)}
.df-ui input[type=number]::-webkit-inner-spin-button,.df-ui input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
.df-ui input[type=number]{-moz-appearance:textfield;text-align:center}
.df-ui input.switch{appearance:none;-webkit-appearance:none;flex:none;width:36px;height:20px;border-radius:10px;background:var(--df-track);position:relative;
margin:0;cursor:pointer;transition:background .15s}
.df-ui input.switch::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:var(--df-knob);
box-shadow:0 1px 2px rgb(0 0 0/.3);transition:left .15s}
.df-ui input.switch:checked{background:var(--df-primary)}.df-ui input.switch:checked::after{left:18px;background:#fff}
.df-ui .muted{color:var(--df-muted)}.df-ui .empty{color:var(--df-muted);font-style:italic}
.df-pop{--df-fg:var(--fg-color,#fff);--df-primary:var(--primary-background,#0b8ce9);--df-link:color-mix(in srgb,#1e88e5 60%,var(--df-fg));
font:13px var(--font-inter,Inter,sans-serif);background:var(--comfy-menu-bg,#353535);color:var(--df-fg);border:1px solid var(--border-color,#4e4e4e);
border-radius:var(--radius-md,6px);box-shadow:0 6px 20px rgb(0 0 0/.4);--df-pop-hover:color-mix(in srgb,var(--comfy-menu-bg,#353535) 85%,var(--df-fg));
--df-pop-on:color-mix(in srgb,var(--df-primary) 35%,var(--comfy-menu-bg,#353535))}
`;
// First in <head>: a panel's own rules of the same specificity, added later, win over these.
export function addThemeStyle() {
  if (document.getElementById("df-theme")) return;
  const style = document.createElement("style");
  style.id = "df-theme";
  style.textContent = THEME;
  document.head.prepend(style);
}
