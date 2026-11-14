import { LuInfo } from "react-icons/lu";

/**
 * Short, collapsible measurement guidance for manual entry forms.
 * Content is conventional (Earth-based) measurement practice. It is NOT a validated spacecraft procedure:
 * wherever posture, gravity or equipment positioning matters, the astronaut is pointed to the
 * mission-approved device instructions. No clinical thresholds are given here.
 */
type Guide = {
  what: string;
  equipment?: string;
  how: string[];
  stable?: string;
  units?: string;
  caution?: string[];
  space?: string;
};

const MICROGRAVITY =
  "Steps below are conventional Earth-based guidance. Where posture, arm position or device placement matters, follow your device's mission-approved microgravity operating instructions.";

export const GUIDES: Record<string, Guide> = {
  bp: {
    what: "The pressure in your arteries when the heart beats (systolic) and between beats (diastolic).",
    equipment: "Blood pressure monitor with a correctly sized cuff.",
    how: [
      "Rest quietly for a few minutes first.",
      "Use the measurement position given in the device instructions.",
      "With a conventional cuff, keep the arm supported at heart level.",
      "Don't talk or move during the reading.",
    ],
    stable: "Wait until the device finishes and shows both values.",
    units: "Systolic and diastolic, both in mmHg.",
    caution: ["A wrong cuff size or arm position can shift the reading."],
    space: MICROGRAVITY,
  },
  hr: {
    what: "How many times your heart beats per minute.",
    equipment: "Heart-rate monitor, wearable or approved pulse-measuring device.",
    how: [
      "For a resting value, rest quietly first.",
      "If counting manually, use the pulse-counting method you were trained on.",
    ],
    stable: "Record a steady value, not a momentary spike or drop.",
    units: "Beats per minute (bpm). Set Activity to resting, exercise or post-exercise.",
    caution: ["Resting values are compared with your own resting baseline, so label the context correctly."],
  },
  spo2: {
    what: "The percentage of your blood's oxygen-carrying capacity that is in use (oxygen saturation).",
    equipment: "Pulse oximeter or supported SpO₂ sensor.",
    how: ["Place the sensor as the device instructions describe.", "Keep still, with the finger or site warm."],
    stable: "Wait until the number stops changing before recording.",
    units: "Percent (%), with the measurement time.",
    caution: ["Movement, poor sensor contact or cold fingers can make the reading inaccurate. Mark the quality as questionable if so."],
    space: MICROGRAVITY,
  },
  temp: {
    what: "Your body temperature.",
    equipment: "Approved medical thermometer.",
    how: ["Follow the thermometer's instructions for the method you use (oral, tympanic or skin).", "Use the same method each time when you can."],
    stable: "Wait for the device's completion signal.",
    units: "°C or °F, and select the method used.",
    caution: ["Different methods give different readings, so values from different methods are not directly comparable."],
  },
  glu: {
    what: "The amount of glucose (sugar) in your blood.",
    equipment: "Approved glucose meter and its compatible test strips or supplies.",
    how: [
      "Measure only according to your prescribed monitoring schedule.",
      "Follow the meter's instructions and the applicable hygiene procedures.",
    ],
    stable: "Wait for the meter to display the result.",
    units: "mg/dL or mmol/L. Also record the time and context (fasting, before or after a meal, after exercise).",
    caution: ["Use only supplies that match your meter."],
    space: "Follow the mission-approved procedure for sample handling and supply disposal.",
  },
  rr: {
    what: "How many breaths you take per minute.",
    equipment: "Approved respiratory monitoring device, or manual counting.",
    how: [
      "For a resting value, measure while resting.",
      "Breathe normally. Don't speed up or slow down your breathing on purpose.",
      "When counting manually, count breaths for a full minute.",
    ],
    units: "Breaths per minute. Select whether it was counted or a wearable estimate.",
    caution: ["Knowing you are being measured can change breathing, so try to breathe naturally."],
  },
  sleep: {
    what: "How long and how well you actually slept.",
    how: [
      "Enter when you fell asleep and when you woke up, not just the time in your sleep station.",
      "If you were awake for part of the night, enter your actual sleep time.",
      "Add awakenings and rate quality and restfulness if you can.",
    ],
    units: "Times in your local time. Duration in hours.",
    caution: ["Shift work, schedule changes and unusual mission timelines can affect sleep. Record what actually happened."],
  },
  mood: {
    what: "A short self-assessment of how you feel right now.",
    how: [
      "Answer based on how you feel now, not how you think you should feel.",
      "Use the scales the same way each day.",
      "Honest answers are the most useful. There are no right or wrong answers.",
    ],
    caution: ["This is a self-assessment, not a psychiatric diagnosis."],
  },
  exercise: {
    what: "Your exercise countermeasure sessions: resistance exercise, treadmill or cycling.",
    how: [
      "Record the exercise name and type (resistive for resistance, aerobic for treadmill or cycling).",
      "Enter duration, intensity and whether you completed it, did part of it or skipped it.",
      "Add performance results (for example grip strength) if available.",
      "Use Notes and Pain for fatigue or discomfort.",
    ],
    units: "Duration in minutes. Pain on a 0–10 scale.",
    caution: ["Exercise records show what you did. They do not measure bone density."],
  },
  nutrition: {
    what: "What you drank and ate.",
    how: [
      "Log each drink or meal separately, close to when you had it.",
      "Record the actual amount consumed, not what was planned, whenever possible.",
      "Use the food name as it appears on the package.",
      "Add appetite or digestive symptoms if you have any.",
    ],
    units: "Water or fluid in mL. Energy in kcal, if known.",
  },
};

export function MeasureGuide({ id }: { id: keyof typeof GUIDES | string }) {
  const g = GUIDES[id];
  if (!g) return null;
  return (
    <details className="measure-guide">
      <summary><LuInfo aria-hidden /> How to measure</summary>
      <dl>
        <dt>What it is</dt><dd>{g.what}</dd>
        {g.equipment && <><dt>You need</dt><dd>{g.equipment}</dd></>}
        <dt>How</dt><dd><ul>{g.how.map((s) => <li key={s}>{s}</li>)}</ul></dd>
        {g.stable && <><dt>Stable reading</dt><dd>{g.stable}</dd></>}
        {g.units && <><dt>Enter</dt><dd>{g.units}</dd></>}
        {g.caution && <><dt>Note</dt><dd>{g.caution.join(" ")}</dd></>}
      </dl>
      {g.space && <p className="measure-space">{g.space}</p>}
    </details>
  );
}
