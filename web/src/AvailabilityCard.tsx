import { useEffect, useState } from "react";
import { getAvailability } from "./api";
import type { Availability } from "./types";

export default function AvailabilityCard({ area }: { area: unknown }) {
  const [data, setData] = useState<Availability | null>(null);

  useEffect(() => {
    getAvailability(area).then(setData);
  }, [area]);

  if (!data) return <p>Checking NISAR data...</p>;

  return (
    <div style={{ background: "#0f1a2c", color: "#e6edf3", padding: 16, borderRadius: 8, width: 320 }}>
      <div style={{ color: "#7dd3fc", fontSize: 12 }}>CHECK DATA</div>
      <h3 style={{ margin: "4px 0" }}>{data.enough ? "ENOUGH DATA" : "NOT ENOUGH DATA"}</h3>
      <p style={{ color: "#9aa4b2", fontSize: 13 }}>
        A fair comparison needs 2 good passes before and 2 after a date.
      </p>
      <div style={{ display: "flex", gap: 16 }}>
        <div><b>{data.goodPasses}</b><div>good passes</div></div>
        <div><b>{data.validated}</b><div>validated</div></div>
        <div><b>{data.provisional}</b><div>provisional</div></div>
        <div><b>{data.dropped}</b><div>dropped</div></div>
      </div>
      <p style={{ color: "#9aa4b2", fontSize: 12 }}>
        No data {data.gap.from} to {data.gap.to}
      </p>
      <p style={{ color: "#f59e0b", fontSize: 12 }}>SAMPLE DATA</p>
    </div>
  );
}