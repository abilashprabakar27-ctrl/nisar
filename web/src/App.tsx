import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import SearchBox from "./SearchBox";
import AvailabilityCard from "./AvailabilityCard";

function boxAround(lng: number, lat: number, widthKm = 18, heightKm = 14) {
  const dLat = heightKm / 2 / 111;
  const dLng = widthKm / 2 / (111 * Math.cos((lat * Math.PI) / 180));
  return [[
    [lng - dLng, lat - dLat], [lng + dLng, lat - dLat],
    [lng + dLng, lat + dLat], [lng - dLng, lat + dLat],
    [lng - dLng, lat - dLat],
  ]];
}

export default function App() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [area, setArea] = useState<[number, number] | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [0, 20],
      zoom: 1.5,
    });

    m.on("click", (e) => {
      const data = {
        type: "Feature" as const,
        properties: {},
        geometry: {
          type: "Polygon" as const,
          coordinates: boxAround(e.lngLat.lng, e.lngLat.lat),
        },
      };
      const src = m.getSource("area") as maplibregl.GeoJSONSource | undefined;
      if (src) {
        src.setData(data);
      } else {
        m.addSource("area", { type: "geojson", data });
        m.addLayer({ id: "area-fill", type: "fill", source: "area", paint: { "fill-color": "#7dd3fc", "fill-opacity": 0.2 } });
        m.addLayer({ id: "area-line", type: "line", source: "area", paint: { "line-color": "#7dd3fc", "line-width": 2 } });
      }
      setArea([e.lngLat.lng, e.lngLat.lat]);
    });

    setMap(m);
    return () => m.remove();
  }, []);

  function clearArea() {
    if (!map) return;
    if (map.getLayer("area-fill")) map.removeLayer("area-fill");
    if (map.getLayer("area-line")) map.removeLayer("area-line");
    if (map.getSource("area")) map.removeSource("area");
    setArea(null);
  }

  return (
    <div style={{ position: "relative", width: "100vw", height: "100vh" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <SearchBox map={map} />
      {area && (
        <div style={{ position: "absolute", top: 80, left: 10, zIndex: 1 }}>
          <AvailabilityCard area={area} />
          <button onClick={clearArea} style={{ marginTop: 8 }}>Clear area</button>
        </div>
      )}
    </div>
  );
}