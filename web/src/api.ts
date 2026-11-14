import type { Sample, Availability } from "./types";

// Flip to false when Arshad's server is live. Screens never call fetch directly.
const USE_SAMPLE = true;
const SERVER = import.meta.env.VITE_API_URL as string | undefined;

export async function getSample(): Promise<Sample> {
  if (USE_SAMPLE) {
    const res = await fetch("/golden-sample.json");
    return res.json();
  }
  throw new Error("Server not connected yet");
}

export async function getAvailability(area: unknown): Promise<Availability> {
  if (USE_SAMPLE) {
    return (await getSample()).availability;
  }
  const res = await fetch(`${SERVER}/availability`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(area),
  });
  return res.json();
}