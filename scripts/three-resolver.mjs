/* =========================================================
   KIRA // NODE RESOLVE HOOK FOR ui/app.js

   Browsers resolve "three" and "three/addons/…" through the import map in
   ui/index.html. Node has no import map, so this hook points the same
   specifiers at the vendored files under ui/vendor/.

   Set KIRA_UI_NO_THREE=1 to make "three" unresolvable on purpose — that
   simulates a browser with no WebGL/no internet and proves app.js degrades
   to its CSS core instead of breaking.

   Used only by scripts/check_ui.mjs; nothing ships this to the browser.
   ========================================================= */

import { pathToFileURL } from "node:url";
import path from "node:path";

const UI = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "ui");

const ADDON_ROOT = "three/addons/";

export async function resolve(specifier, context, nextResolve) {
  if (process.env.KIRA_UI_NO_THREE) {
    return nextResolve(specifier, context);
  }

  if (specifier === "three") {
    return {
      url: pathToFileURL(path.join(UI, "vendor", "three.module.min.js")).href,
      shortCircuit: true,
    };
  }

  if (specifier.startsWith(ADDON_ROOT)) {
    const relative = specifier.slice(ADDON_ROOT.length);
    return {
      url: pathToFileURL(path.join(UI, "vendor", "jsm", relative)).href,
      shortCircuit: true,
    };
  }

  return nextResolve(specifier, context);
}
