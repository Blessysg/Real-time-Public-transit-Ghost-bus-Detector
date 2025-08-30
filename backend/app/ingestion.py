import aiohttp
import asyncio,time
from google.transit import gtfs_realtime_pb2
import redis,json
import aioredis
import requests

@app.get("/fetch_buses")
def fetch_buses()
url="https://developers.google.com/transit/gtfs/examples/gtfs-feed"
response=requests.get(url)
return("data":response.json())

REDIS=redis.Redis(host='redis',port=6379)

async with aiohttp.ClientSession() as session:
    async with session.get(url)as resp:
        return await resp.read()

async def parse_and_publish(feed_bytes):
    feed=gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(feed_bytes)
    for entity in feed.entity:
        if entity.HasField('vehicle'):
            v=entity.vehicle
            msg={
                'vehicle_id':v.vehicle.id,
                'trip_id':v.trip.trip_id,
                'route_id':v.trip.route_id,
                'lat':v.position.latitude,
                'lon':v.position.longitude,
                'speed':getattr(v.position,'speed',None),
                'timestamp':v.timestamp
            }
            #store in redis
            REDIS.hmset(f"vehicle:{msg['vehicle_id']}",msg)
            REDIS.expire(f"vehicle:{msg['vehicle_id']}",180)
            
            #publish to bus channel
            REDIS.publish('vehicles:updates',json.dumps(msg))

async def loop(url,interval=10):
    while True:
        try:
            raw=await fetch_feed(url)
            await parse_and_publish(raw)
        except Eception as e:
            print("error",e)
            await asyncio.sleep(interval)