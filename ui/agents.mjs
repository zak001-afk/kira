// KIRA agent registry — add a new agent by appending one entry here.
// The interface (left list, floating modules, activity meters, connection
// lines) renders itself from this configuration. No per-agent UI code.
//
// action: exactly one of prompt (prefills the command box), command
// (sent to KIRA immediately) or dialog (opens a control panel).
// metric: which real session activity drives the agent's meter.
export const AGENTS = [
  {
    id: "data",
    name: "Data Analyst",
    description: "Analysis & reports",
    icon: "i-data",
    chip: "a",
    action: { prompt: "analyse " },
    metric: "memory",
  },
  {
    id: "web",
    name: "Web Developer",
    description: "Sites & applications",
    icon: "i-code",
    chip: "b",
    action: { command: "open chrome" },
    metric: "opens",
  },
  {
    id: "content",
    name: "Content Creator",
    description: "Media & networks",
    icon: "i-pen",
    chip: "c",
    action: { prompt: "écris " },
    metric: "voice",
  },
  {
    id: "system",
    name: "System Manager",
    description: "System & maintenance",
    icon: "i-settings",
    chip: "e",
    action: { command: "system info" },
    metric: "cpu",
  },
  {
    id: "research",
    name: "Research Agent",
    description: "Information research",
    icon: "i-search",
    chip: "d",
    action: { prompt: "search for " },
    chipAction: { prompt: "cherche " },
    metric: "searches",
  },
  {
    id: "automation",
    name: "Automation Agent",
    description: "Task execution",
    icon: "i-nodes",
    chip: "f",
    action: { dialog: "tasks" },
    metric: "tasks",
  },
];

// Classification used by the orchestration display: which agent a plain
// command is delegated to (same regexes the session counters use).
export function delegateFor(text) {
  const lowered = String(text).toLowerCase();
  if (/\b(search|cherche|recherche|find|trouve|locate)\b/.test(lowered)) return "research";
  if (/\b(open|ouvre|launch|lance)\b/.test(lowered)) return "automation";
  if (/\b(system info|infos?( système|tem)?|systeme)\b/.test(lowered)) return "system";
  return null;
}
