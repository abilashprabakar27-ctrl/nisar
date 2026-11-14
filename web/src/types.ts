export type Quality = "validated" | "provisional" | "dropped";

export type Availability = {
  enough: boolean;
  goodPasses: number;
  validated: number;
  provisional: number;
  dropped: number;
  track: string;
  passes: { date: string; quality: Quality }[];
  gap: { from: string; to: string };
};

export type Sample = {
  dataMode: "sample" | "saved" | "live";
  area: { name: string; center: [number, number]; hectares: number };
  availability: Availability;
};