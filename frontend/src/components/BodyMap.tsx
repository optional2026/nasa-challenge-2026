// Interactive anatomical map. Each region is a focusable button that selects a body system.
import { Tone } from "../lib/format";

export const SYSTEMS: { id: string; label: string }[] = [
  { id: "neurological", label: "Neurological, sensorimotor & vision" },
  { id: "behavioral", label: "Behavioral health" },
  { id: "cardiovascular", label: "Cardiovascular" },
  { id: "respiratory", label: "Respiratory" },
  { id: "immune", label: "Immune" },
  { id: "musculoskeletal", label: "Musculoskeletal" },
  { id: "renal_metabolic", label: "Renal, nutrition & metabolic" },
];

export function BodyMap({ selected, onSelect, tones }: { selected: string; onSelect: (id: string) => void; tones: Record<string, Tone> }) {
  const region = (id: string, children: any) => (
    <g className={`region region-${id} ${selected === id ? "selected" : ""} tone-${tones[id] || "none"}`}
      role="button" tabIndex={0} aria-pressed={selected === id} aria-label={SYSTEMS.find((s) => s.id === id)?.label}
      onClick={() => onSelect(id)} onKeyDown={(e: any) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(id); } }}>
      <title>{SYSTEMS.find((s) => s.id === id)?.label}</title>
      {children}
    </g>
  );
  return (
    <svg viewBox="0 0 240 470" className="bodymap" aria-label="Body systems map">
      {/* silhouette */}
      <g className="silhouette" aria-hidden>
        <ellipse cx="120" cy="52" rx="30" ry="36" />
        <rect x="108" y="84" width="24" height="18" rx="6" />
        <path d="M70 108 Q120 92 170 108 L182 230 Q178 250 168 252 L160 300 L80 300 L72 252 Q62 250 58 230 Z" />
        <path d="M70 110 L44 200 L36 268 L50 272 L62 206 L80 150 Z" />
        <path d="M170 110 L196 200 L204 268 L190 272 L178 206 L160 150 Z" />
        <path d="M82 296 L76 380 L80 452 L104 452 L106 380 L116 300 Z" />
        <path d="M158 296 L164 380 L160 452 L136 452 L134 380 L124 300 Z" />
      </g>
      {region("behavioral", <circle cx="120" cy="50" r="46" className="halo" />)}
      {region("neurological", <>
        <path d="M96 44 Q98 20 120 18 Q142 20 144 44 Q140 56 120 58 Q100 56 96 44 Z" />
        <line x1="120" y1="60" x2="120" y2="250" className="nerve" />
      </>)}
      {region("immune", <>
        <circle cx="104" cy="96" r="6" /><circle cx="136" cy="96" r="6" />
        <circle cx="80" cy="128" r="6" /><circle cx="160" cy="128" r="6" />
        <circle cx="96" cy="262" r="6" /><circle cx="144" cy="262" r="6" />
      </>)}
      {region("respiratory", <>
        <path d="M84 126 Q100 116 112 130 L112 196 Q96 206 84 196 Z" />
        <path d="M156 126 Q140 116 128 130 L128 196 Q144 206 156 196 Z" />
      </>)}
      {region("cardiovascular", <path d="M120 186 C102 172 104 150 118 154 C120 155 120 158 120 160 C120 158 120 155 122 154 C136 150 138 172 120 186 Z" transform="translate(-2 -10) scale(1.02)" />)}
      {region("renal_metabolic", <>
        <ellipse cx="102" cy="230" rx="9" ry="14" /><ellipse cx="138" cy="230" rx="9" ry="14" />
        <path d="M100 208 Q120 198 140 208 L136 220 Q120 214 104 220 Z" />
      </>)}
      {region("musculoskeletal", <>
        <path d="M58 214 L48 266" className="bone" /><path d="M182 214 L192 266" className="bone" />
        <path d="M92 312 L90 440" className="bone" /><path d="M148 312 L150 440" className="bone" />
        <path d="M78 290 Q120 306 162 290" className="bone" />
      </>)}
    </svg>
  );
}
