
# main.py - Ghost Bus Detection FastAPI Backend
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import asyncio
import json
import time
import math
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
import redis
import redis.asyncio as redis
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn


# Data Models
class BusUpdate(BaseModel):
    vehicle_id: str
    lat: float
    lon: float
    route_id: Optional[str] = None
    trip_id: Optional[str] = None
    speed: Optional[float] = None
    bearing: Optional[float] = None
    timestamp: Optional[float] = None


class BusResponse(BaseModel):
    vehicle_id: str
    lat: float
    lon: float
    route_id: Optional[str] = None
    speed: Optional[float] = None
    is_ghost: bool = False
    ghost_score: float = 0.0
    status: str = "active"
    anomaly: bool = False
    anomaly_types: List[str] = []
    severity: str = "info"
    last_update: str = ""


class SystemStats(BaseModel):
    total_buses: int
    active_buses: int
    ghost_buses: int
    ghost_percentage: float
    last_updated: str


# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []


    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)


    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)


    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except:
                disconnected.append(connection)
        
        # Remove disconnected connections
        for conn in disconnected:
            self.disconnect(conn)


# Ghost Detection Engine
class GhostDetector:
    def __init__(self, redis_client):
        self.redis = redis_client
        
    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in meters"""
        R = 6371000.0  # Earth radius in meters
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
             math.sin(dlon/2)**2)
        return 2 * R * math.asin(math.sqrt(a))
    
    async def push_series(self, key: str, value: float, window: int = 60):
        """Store time series data in Redis"""
        await self.redis.lpush(key, str(value))
        await self.redis.ltrim(key, 0, window - 1)
    
    async def get_moving_stats(self, key: str) -> Optional[dict]:
        """Calculate moving average and std deviation"""
        vals = await self.redis.lrange(key, 0, -1)
        if not vals or len(vals) < 5:
            return None
            
        vals = [float(v) for v in vals]
        avg = sum(vals) / len(vals)
        std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        return {"avg": avg, "std": std, "count": len(vals)}
    
    async def detect_anomalies(self, bus_data: dict) -> tuple:
        """Main anomaly detection logic"""
        vehicle_id = bus_data["vehicle_id"]
        anomaly_types = []
        severity = "info"
        now = time.time()
        
        # 1. Stale data detection - lowered for testing
        last_ts = bus_data.get("timestamp", now)
        if now - last_ts > 20:  # Lowered from 120 to 20 seconds
            anomaly_types.append("stale")
            severity = "warning"
        
        # 2. Not moving detection (track recent positions)
        loc_key = f"vehicle:{vehicle_id}:locations"
        location_data = {
            "lat": bus_data["lat"],
            "lon": bus_data["lon"], 
            "timestamp": last_ts
        }
        
        await self.redis.lpush(loc_key, json.dumps(location_data))
        await self.redis.ltrim(loc_key, 0, 10)  # Keep last 10 positions
        
        # Check if bus has moved
        locations_raw = await self.redis.lrange(loc_key, 0, -1)
        if len(locations_raw) >= 5:
            locations = [json.loads(loc) for loc in locations_raw]
            total_distance = 0.0
            
            for i in range(len(locations) - 1):
                loc1, loc2 = locations[i], locations[i + 1]
                total_distance += self.haversine_distance(
                    loc1["lat"], loc1["lon"], 
                    loc2["lat"], loc2["lon"]
                )
            
            if total_distance < 5:  # Less than 20m movement across updates
                anomaly_types.append("not_moving")
                if severity == "info":
                    severity = "warning"
        
        # 3. Speed anomaly detection
        if "speed" in bus_data and bus_data["speed"] is not None:
            speed_key = f"vehicle:{vehicle_id}:speed"
            await self.push_series(speed_key, float(bus_data["speed"]))
            
            stats = await self.get_moving_stats(speed_key)
            if stats:
                current_speed = bus_data["speed"]
                if current_speed > stats["avg"] * 3:
                    anomaly_types.append("speed_spike")
                elif stats["avg"] > 0 and current_speed < stats["avg"] * 0.3:
                    anomaly_types.append("speed_drop")
        
        # 4. Calculate ghost score
        ghost_score = 0.0
        if "stale" in anomaly_types:
            ghost_score += 0.4
        if "not_moving" in anomaly_types:
            ghost_score += 0.25
        if "speed_drop" in anomaly_types:
            ghost_score += 0.2
        
        # Determine final severity
        if len(anomaly_types) >= 2:
            severity = "critical"
        elif ghost_score > 0.3:
            severity = "warning"
            
        is_ghost = ghost_score >= 0.6
        status = "ghost" if is_ghost else "active"
        
        return len(anomaly_types) > 0, anomaly_types, severity, ghost_score, is_ghost, status


# Initialize FastAPI app
app = FastAPI(title="Ghost Bus Detection API", version="1.0.0")


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global state
manager = ConnectionManager()
ghost_detector = None
redis_client = None
STATE: Dict[str, dict] = {}


@app.on_event("startup")
async def startup_event():
    global ghost_detector, redis_client
    try:
        redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
        ghost_detector = GhostDetector(redis_client)
        
        # Start bus simulator
        asyncio.create_task(bus_simulator())
        print("✅ Redis connected and simulator started")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("⚠️ Running without Redis (in-memory only)")


@app.on_event("shutdown") 
async def shutdown_event():
    if redis_client:
        await redis_client.close()


# API Endpoints
@app.get("/")
async def root():
    return {
        "message": "Ghost Bus Detection API is running",
        "version": "1.0.0",
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/buses", response_model=List[BusResponse])
async def get_all_buses(include_ghost: bool = True, route_id: Optional[str] = None):
    """Get all current bus positions with ghost detection data"""
    buses = []
    
    for vehicle_id, bus_data in STATE.items():
        if route_id and bus_data.get("route_id") != route_id:
            continue
            
        if not include_ghost and bus_data.get("is_ghost", False):
            continue
            
        bus_response = BusResponse(
            vehicle_id=vehicle_id,
            lat=bus_data["lat"],
            lon=bus_data["lon"],
            route_id=bus_data.get("route_id"),
            speed=bus_data.get("speed"),
            is_ghost=bus_data.get("is_ghost", False),
            ghost_score=bus_data.get("ghost_score", 0.0),
            status=bus_data.get("status", "active"),
            anomaly=bus_data.get("anomaly", False),
            anomaly_types=bus_data.get("anomaly_types", []),
            severity=bus_data.get("severity", "info"),
            last_update=bus_data.get("last_update", "")
        )
        buses.append(bus_response)
    
    return buses


@app.get("/buses/{vehicle_id}")
async def get_bus_details(vehicle_id: str):
    """Get detailed information for a specific bus"""
    if vehicle_id not in STATE:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found")
    
    bus_data = STATE[vehicle_id]
    return {
        "vehicle_id": vehicle_id,
        "current_position": {
            "lat": bus_data["lat"],
            "lon": bus_data["lon"],
            "timestamp": bus_data.get("timestamp", time.time())
        },
        "is_ghost": bus_data.get("is_ghost", False),
        "ghost_score": bus_data.get("ghost_score", 0.0),
        "anomaly_details": {
            "types": bus_data.get("anomaly_types", []),
            "severity": bus_data.get("severity", "info")
        },
        "route_info": {
            "route_id": bus_data.get("route_id"),
            "trip_id": bus_data.get("trip_id")
        }
    }


@app.get("/active_buses")
async def get_active_buses():
    """Get only active (non-ghost) buses"""
    active = [bus for bus in STATE.values() if not bus.get("is_ghost", False)]
    return {"active_buses": active, "count": len(active)}


@app.get("/ghost_buses")
async def get_ghost_buses():
    """Get only ghost buses with detection details"""
    ghost = [bus for bus in STATE.values() if bus.get("is_ghost", False)]
    return {"ghost_buses": ghost, "count": len(ghost)}


@app.get("/stats", response_model=SystemStats)
async def get_system_stats():
    """Get system-wide statistics"""
    total = len(STATE)
    ghost_count = sum(1 for bus in STATE.values() if bus.get("is_ghost", False))
    active_count = total - ghost_count
    
    return SystemStats(
        total_buses=total,
        active_buses=active_count,
        ghost_buses=ghost_count,
        ghost_percentage=round((ghost_count / total * 100) if total > 0 else 0, 1),
        last_updated=datetime.now().isoformat()
    )


@app.post("/update_bus")
async def update_bus_position(bus_update: BusUpdate):
    """Manually update bus position (for testing)"""
    vehicle_id = bus_update.vehicle_id
    
    # Convert to dict for processing
    bus_data = bus_update.dict()
    bus_data["timestamp"] = bus_data.get("timestamp") or time.time()
    bus_data["last_update"] = datetime.now().isoformat()
    
    # Run ghost detection if available
    if ghost_detector:
        try:
            anomaly, types, severity, score, is_ghost, status = await ghost_detector.detect_anomalies(bus_data)
            bus_data.update({
                "anomaly": anomaly,
                "anomaly_types": types, 
                "severity": severity,
                "ghost_score": score,
                "is_ghost": is_ghost,
                "status": status
            })
        except Exception as e:
            print(f"Detection error: {e}")
    
    # Store in state
    STATE[vehicle_id] = bus_data
    
    # Broadcast to WebSocket clients
    await manager.broadcast({
        "type": "bus.update",
        "data": bus_data
    })
    
    return {
        "success": True,
        "vehicle_id": vehicle_id,
        "ghost_score": bus_data.get("ghost_score", 0.0),
        "is_ghost": bus_data.get("is_ghost", False),
        "anomalies_detected": bus_data.get("anomaly_types", [])
    }


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        # Send initial snapshot
        await websocket.send_text(json.dumps({
            "type": "snapshot",
            "data": list(STATE.values())
        }))
        
        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Bus Simulator (for demo purposes)
async def bus_simulator():
    """Simulate bus movements for testing"""
    await asyncio.sleep(2)  # Wait for startup
    
    # Define some routes around Bangalore coordinates
    routes = {
        "R1": {"lat": 12.9716, "lon": 77.5946, "buses": ["B101", "B102", "B103"]},
        "R2": {"lat": 12.9750, "lon": 77.6000, "buses": ["B201", "B202"]},
        "R3": {"lat": 12.9800, "lon": 77.5900, "buses": ["B301", "B302", "B303"]}
    }
    
    step = 0
    while True:
        try:
            for route_id, route_info in routes.items():
                base_lat = route_info["lat"] 
                base_lon = route_info["lon"]
                
                for i, bus_id in enumerate(route_info["buses"]):
                    # Simulate movement
                    lat_offset = math.sin(step * 0.1 + i) * 0.01  # ~1km variation
                    lon_offset = math.cos(step * 0.1 + i) * 0.01
                    
                    # Make B103 and B302 behave like ghost buses (more stale updates)
                    if bus_id in ["B103", "B302"]:
                        if step % 10 < 8:  # Increased stale time to 80% of updates
                            continue  # Skip update to make it stale
                        # Make them not move much
                        lat_offset *= 0.1
                        lon_offset *= 0.1
                    
                    bus_update = BusUpdate(
                        vehicle_id=bus_id,
                        lat=base_lat + lat_offset,
                        lon=base_lon + lon_offset, 
                        route_id=route_id,
                        trip_id=f"T{route_id[1:]}-{i+1}",
                        speed=20 + i * 5 + (5 * math.sin(step * 0.1)),
                        bearing=45 + (step * 2) % 360,
                        timestamp=time.time()
                    )
                    
                    # Process the update
                    await update_bus_position(bus_update)
            
            step += 1
            await asyncio.sleep(5)  # Update every 5 seconds
            
        except Exception as e:
            print(f"Simulator error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
