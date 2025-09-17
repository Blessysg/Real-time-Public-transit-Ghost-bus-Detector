import time
import math

class GhostDetector:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def is_data_stale(self, bus_data, threshold_seconds=90):
        """Check if bus hasn't updated recently"""
        current_time = time.time()
        bus_time = bus_data.get('timestamp', 0)
        return (current_time - bus_time) > threshold_seconds
    
    def is_bus_stuck(self, bus_id):
        """Check if bus hasn't moved in a while"""
        # Get last few positions from Redis
        # Compare them to see if bus is stuck
        # This is simplified - you'd implement full logic here
        return False
    
    def calculate_ghost_score(self, bus_data):
        """Give each bus a 'ghost score' from 0-1"""
        score = 0
        
        # Add points for suspicious behavior
        if self.is_data_stale(bus_data):
            score += 0.4
        
        if self.is_bus_stuck(bus_data['id']):
            score += 0.3
        
        # Add more detection rules here
        
        return min(score, 1.0)  # Cap at 1.0
    
    def is_ghost_bus(self, bus_data):
        """Decide if this bus is a ghost"""
        score = self.calculate_ghost_score(bus_data)
        return score > 0.6  # Threshold for calling it a ghost
