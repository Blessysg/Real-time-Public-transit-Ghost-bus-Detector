import aiohttp
import asyncio
from google.transit import gtfs_realtime_pb2
import redis
import json
import time

class BusDataIngester:
    def __init__(self, feed_url, redis_client):
        self.feed_url = feed_url  # Your city's bus data URL
        self.redis = redis_client
    
    async def fetch_bus_data(self):
        """Get bus data from the city's system"""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.feed_url) as response:
                return await response.read()
    
    async def process_bus_data(self, raw_data):
        """Turn raw data into something useful"""
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(raw_data)
        
        buses = []
        for entity in feed.entity:
            if entity.HasField('vehicle'):
                v = entity.vehicle
                bus_info = {
                    'id': v.vehicle.id,
                    'route': v.trip.route_id,
                    'lat': v.position.latitude,
                    'lon': v.position.longitude,
                    'timestamp': v.timestamp,
                    'is_ghost': False  # We'll detect this later
                }
                buses.append(bus_info)
                
                # Save to Redis
                self.redis.set(f"bus:{bus_info['id']}", json.dumps(bus_info))
        
        return buses
