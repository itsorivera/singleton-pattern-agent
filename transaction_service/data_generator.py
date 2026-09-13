"""
Transaction Data Generator
Generates realistic transaction data using Faker library.
"""

import random
from datetime import datetime, timezone
from typing import Dict, Any

from faker import Faker


class TransactionGenerator:
    """Generates simulated transaction data for testing the agent."""
    
    # Predefined locations matching the location service
    LOCATIONS = [
        {"city": "Ciudad de México", "latitude": 19.4326, "longitude": -99.1332},
        {"city": "New York", "latitude": 40.7128, "longitude": -74.0060},
        {"city": "London", "latitude": 51.5074, "longitude": -0.1278},
        {"city": "Tokyo", "latitude": 35.6762, "longitude": 139.6503},
        {"city": "Paris", "latitude": 48.8566, "longitude": 2.3522},
        {"city": "Sydney", "latitude": -33.8688, "longitude": 151.2093},
        {"city": "Berlin", "latitude": 52.5200, "longitude": 13.4050},
        {"city": "Singapore", "latitude": 1.3521, "longitude": 103.8198},
        {"city": "Toronto", "latitude": 43.6532, "longitude": -79.3832},
        {"city": "São Paulo", "latitude": -23.5505, "longitude": -46.6333},
        {"city": "Dubai", "latitude": 25.2048, "longitude": 55.2708},
        {"city": "Mumbai", "latitude": 19.0760, "longitude": 72.8777},
    ]
    
    # Query templates for different types of user queries
    QUERY_TEMPLATES = [
        "¿Cuál es el clima en mi ubicación?",
        "What's the weather like here?",
        "Tell me about the current weather conditions",
        "¿Qué hora es en {city}?",
        "What time is it in {city}?",
        "Give me information about {city}",
        "¿Cuál es la población de {city}?",
        "What's the population of {city}?",
        "Tell me about the demographics of {city}",
        "What's the timezone in {city}?",
        "¿Cuál es la zona horaria de {city}?",
        "What are the peak hours in {city}?",
        "¿Cuáles son las horas pico en {city}?",
        "Give me weather and demographic info for my location",
        "What's the temperature and humidity here?",
        "Tell me about local conditions in {city}",
    ]
    
    # LLM models to simulate
    LLM_MODELS = [
        "gpt-4",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
        "claude-3-opus",
        "claude-3-sonnet",
        "claude-3-haiku",
    ]
    
    def __init__(self, locale: str = "en_US"):
        """
        Initialize the transaction generator.
        
        Args:
            locale: Faker locale for generating user data
        """
        self.faker = Faker(locale)
        self.transaction_counter = 0
    
    def generate_transaction(self) -> Dict[str, Any]:
        """
        Generate a single simulated transaction.
        
        Returns:
            Dictionary containing transaction data
        """
        self.transaction_counter += 1
        
        # Select random location
        location = random.choice(self.LOCATIONS)
        
        # Generate query (some with city placeholder filled)
        query_template = random.choice(self.QUERY_TEMPLATES)
        if "{city}" in query_template:
            query = query_template.format(city=location["city"])
        else:
            query = query_template
        
        # Generate realistic token usage based on query complexity
        base_tokens = len(query.split()) * 2
        tokens_used = random.randint(base_tokens + 50, base_tokens + 300)
        
        # Generate realistic response time (in milliseconds)
        # Longer queries and more tokens = longer response time
        base_time = 500
        response_time_ms = random.randint(
            base_time + tokens_used,
            base_time + tokens_used * 2
        )
        
        transaction = {
            "transaction_id": f"txn_{self.transaction_counter:06d}",
            "user_id": f"user_{self.faker.uuid4()[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "llm_model": random.choice(self.LLM_MODELS),
            "tokens_used": tokens_used,
            "response_time_ms": response_time_ms,
            "location_metadata": {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "city": location["city"]
            }
        }
        
        return transaction
    
    def generate_batch(self, count: int = 10) -> list[Dict[str, Any]]:
        """
        Generate a batch of transactions.
        
        Args:
            count: Number of transactions to generate
        
        Returns:
            List of transaction dictionaries
        """
        return [self.generate_transaction() for _ in range(count)]
    
    def reset_counter(self):
        """Reset the transaction counter."""
        self.transaction_counter = 0
