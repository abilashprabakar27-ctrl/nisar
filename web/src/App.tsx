import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import SearchBox from "./SearchBox";
import AvailabilityCard from "./AvailabilityCard";

// NASA GIBS NISAR layer (EPSG:3857, confirmed from GIBS capabilities)
const GIBS_LAYER = "NISAR_L2_Geocoded_Polarimetric_Covariance";
const GIBS_MAXZOOM = 13;
const DEFAULT_DATE = "2026-11-10";

const gibsTilesFor = (time: string) =>
  `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi` +
  `?TIME=${time}&layer=${GIBS_LAYER}&style=default` +
  `&tilematrixset=GoogleMapsCompatible_Level13` +
  `&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image%2Fpng` +
  `&TileMatrix={z}&TileCol={x}&TileRow={y}`;

// Fixed-size study area (18 x 14 km, as in the design)
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
  const [date, setDate] = useState(DEFAULT_DATE);

  // Create the map once
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
          nisar: {
            type: "raster",
            tiles: [gibsTilesFor(`${DEFAULT_DATE}T00:00:00Z`)],
            tileSize: 256,
            maxzoom: GIBS_MAXZOOM,
            attribution: "NASA GIBS · NISAR (NASA-ISRO)",
          },
        },
        layers: [
          { id: "osm", type: "raster", source: "osm" },
          {
            id: "nisar",
            type: "raster",
            source: "nisar",
            paint: { "raster-opacity": 0.7 },
          },
        ],
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
        m.addLayer({
          id: "area-fill",
          type: "fill",
          source: "area",
          paint: { "fill-color": "#7dd3fc", "fill-opacity": 0.2 },
        });
        m.addLayer({
          id: "area-line",
          type: "line",
          source: "area",
          paint: { "line-color": "#7dd3fc", "line-width": 2 },
        });
      }
      setArea([e.lngLat.lng, e.lngLat.lat]);
    });

    setMap(m);
    return () => m.remove();
  }, []);

  // Swap the NISAR tiles when the date changes
  useEffect(() => {
    if (!map) return;
    const src = map.getSource("nisar") as maplibregl.RasterTileSource | undefined;
    if (!src) return;
    src.setTiles([gibsTilesFor(`${date}T00:00:00Z`)]);
  }, [date, map]);

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

      <div
        style={{
          position: "absolute",
          top: 10,
          left: 330,
          zIndex: 1,
          background: "white",
          padding: 8,
          borderRadius: 6,
        }}
      >
        <label style={{ fontSize: 12, marginRight: 6 }}>NISAR date</label>
        <input
          type="date"
          value={date}
          min="2026-06-17"
          max="2026-11-13"
          onChange={(e) => setDate(e.target.value)}
        />
      </div>

      {area && (
        <div style={{ position: "absolute", top: 80, left: 10, zIndex: 1 }}>
          <AvailabilityCard area={area} />
          <button onClick={clearArea} style={{ marginTop: 8 }}>
            Clear area
          </button>
        </div>
      )}
    </div>
  );
}