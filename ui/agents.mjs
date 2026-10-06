// KIRA agent registry — add a new agent by appending one entry here.
// The interface (left list, floating modules, activity meters, connection
// lines) renders itself from this configuration. No per-agent UI code.
//
// action: exactly one of prompt (prefills the command box), command
// (sent to KIRA immediately) or dialog (opens a control panel).
// metric: which real session activity drives the agent's meter.
export const AGENTS = [
  {
    id: "programming",
    name: "Agent de programmation",
    description: "Projets complets et modifications de code",
    icon: "i-code",
    chip: "a",
    action: { prompt: "" },
    metric: "memory",
  },
];

// Classification used by the orchestration display: which agent a plain
// command is delegated to (same regexes the session counters use).
export function delegateFor(text) {
  const lowered = String(text).toLowerCase();
  if (/\b(code|coded|coder|programme|program|script|python|bug|refactor)\b/.test(lowered)) return "programming";
  return null;
}
