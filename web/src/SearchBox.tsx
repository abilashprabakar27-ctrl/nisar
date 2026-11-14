import { useState } from "react";
import type { FormEvent } from "react";
import type { Map } from "maplibre-gl";

type Props = { map: Map | null };

type NominatimResult = { lat: string; lon: string; display_name: string };

export default function SearchBox({ map }: Props) {
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!query.trim() || !map) return;
    setError("");
    try {
      const url =
        "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" +
        encodeURIComponent(query);
      const res = await fetch(url);
      const data: NominatimResult[] = await res.json();
      if (data.length === 0) {
        setError("Place not found");
        return;
      }
      const { lat, lon } = data[0];
      map.flyTo({ center: [parseFloat(lon), parseFloat(lat)], zoom: 10 });
    } catch {
      setError("Search failed, try again");
    }
  }

  return (
    <form
      onSubmit={handleSearch}
      style={{ position: "absolute", top: 10, left: 10, zIndex: 1, background: "white", padding: 8, borderRadius: 6 }}
    >
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search a place..."
      />
      <button type="submit">Search</button>
      {error && <div style={{ color: "red" }}>{error}</div>}
    </form>
  );
}