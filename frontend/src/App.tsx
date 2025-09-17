import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import CustomMarker from './components/CustomMarker';  // Import custom marker

type Bus = {
  id: string;
  route: string;
  lat: number;
  lon: number;
  is_ghost: boolean;
};

const realBusIcon = new L.Icon({
  iconUrl: 'https://chart.googleapis.com/chart?chst=d_map_pin_letter&chld=R|00FF00|000000',
  iconSize: [21, 34],
  iconAnchor: [10, 34],
  popupAnchor: [1, -34],
});

const ghostBusIcon = new L.Icon({
  iconUrl: 'https://chart.googleapis.com/chart?chst=d_map_pin_letter&chld=G|FF0000|000000',
  iconSize: [21, 34],
  iconAnchor: [10, 34],
  popupAnchor: [1, -34],
});

const position: [number, number] = [40.7128, -74.0060];

function ChangeView({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();
  map.setView(center, zoom);
  return null;
}

function App() {
  const [buses, setBuses] = useState<Bus[]>([]);
  const [hideGhosts, setHideGhosts] = useState(false);
  const zoom = 13;

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws');

    ws.onmessage = (event) => {
      const busData = JSON.parse(event.data);
      setBuses(busData);
    };

    return () => ws.close();
  }, []);

  const displayedBuses = hideGhosts ? buses.filter(bus => !bus.is_ghost) : buses;

  return (
    <div style={{ height: '100vh', width: '100%' }}>
      <h1>Ghost Bus Detector</h1>
      <label style={{ marginBottom: 10, display: 'block' }}>
        <input
          type="checkbox"
          checked={hideGhosts}
          onChange={(e) => setHideGhosts(e.target.checked)}
        /> Hide Ghost Buses
      </label>

      <MapContainer style={{ height: '80%', width: '100%' }}>
        <ChangeView center={position} zoom={zoom} />
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {displayedBuses.map(bus => (
          <CustomMarker
            key={bus.id}
            bus={bus}
            icon={bus.is_ghost ? ghostBusIcon : realBusIcon}
          />
        ))}
      </MapContainer>
    </div>
  );
}

export default App;
