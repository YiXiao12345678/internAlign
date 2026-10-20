export function greeting(date = new Date()) {
  const hour = date.getHours();
  if (hour < 5) return "Good evening";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function today(date = new Date()) {
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function initials(name = "") {
  return (
    name
      .split(" ")
      .filter(Boolean)
      .map((part) => part[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "U"
  );
}

const LOGO_COLORS = ["purple", "blue", "orange"];
export function logoColor(name = "") {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) % 997;
  return LOGO_COLORS[hash % LOGO_COLORS.length];
}

// "sigmacomputing" -> "Sigmacomputing", "niantic-spatial" -> "Niantic Spatial"
export function prettyCompany(slug = "") {
  return slug
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

// Backend status -> CSS modifier used by the existing stylesheet.
export const STATUS = {
  Supported: { tone: "matched", icon: "✓", label: "Supported" },
  "Partially supported": { tone: "partial", icon: "!", label: "Partial" },
  "Not found": { tone: "missing", icon: "×", label: "Missing" },
};

export function scoreBand(score) {
  if (score == null) return "none";
  if (score >= 70) return "strong";
  if (score >= 50) return "partial";
  return "stretch";
}

export function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
