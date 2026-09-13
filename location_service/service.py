"""
Location Service - Simulated API REST service
Provides location data with weather, demographics, and contextual information.

This service is PROVIDED to candidates - they should NOT modify it.
Candidates must implement an MCP Server that consumes this service.
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


# Data Models
class Weather(BaseModel):
    temperature: float = Field(..., description="Temperature in Celsius")
    condition: str = Field(..., description="Weather condition description")
    humidity: int = Field(..., ge=0, le=100, description="Humidity percentage")
    wind_speed: float = Field(..., ge=0, description="Wind speed in km/h")


class Demographics(BaseModel):
    population: int = Field(..., ge=0, description="Population count")
    language: str = Field(..., description="Primary language(s)")
    currency: str = Field(..., description="Currency code")


class LocationData(BaseModel):
    location_id: str = Field(..., description="Unique location identifier")
    city: str = Field(..., description="City name")
    country: str = Field(..., description="Country name")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    timezone: str = Field(..., description="IANA timezone identifier")
    weather: Weather = Field(..., description="Current weather information")
    observations: list[str] = Field(..., description="Contextual observations about the location")
    demographics: Demographics = Field(..., description="Demographic information")


# Initialize FastAPI app
app = FastAPI(
    title="Location Data Service",
    description="Simulated service providing location data for AI & Data Agent evaluation",
    version="1.0.0",
)


# Load location data
def load_locations() -> list[LocationData]:
    """Load location data from JSON file."""
    data_file = Path(__file__).parent / "locations_data.json"
    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [LocationData(**item) for item in data]


LOCATIONS_DB = load_locations()


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "service": "Location Data Service",
        "status": "running",
        "version": "1.0.0",
        "total_locations": len(LOCATIONS_DB),
    }


@app.get("/locations", response_model=list[LocationData], tags=["Locations"])
async def get_all_locations():
    """
    Get all available locations.
    
    Returns:
        List of all location data entries
    """
    return LOCATIONS_DB


@app.get("/locations/{location_id}", response_model=LocationData, tags=["Locations"])
async def get_location_by_id(location_id: str):
    """
    Get location data by location ID.
    
    Args:
        location_id: Unique location identifier (e.g., 'loc_cdmx_001')
    
    Returns:
        Location data for the specified ID
    
    Raises:
        HTTPException: 404 if location not found
    """
    for location in LOCATIONS_DB:
        if location.location_id == location_id:
            return location
    
    raise HTTPException(
        status_code=404,
        detail=f"Location with ID '{location_id}' not found"
    )


@app.get("/locations/by-city/{city}", response_model=LocationData, tags=["Locations"])
async def get_location_by_city(city: str):
    """
    Get location data by city name (case-insensitive).
    
    Args:
        city: City name (e.g., 'Ciudad de México', 'New York')
    
    Returns:
        Location data for the specified city
    
    Raises:
        HTTPException: 404 if city not found
    """
    city_lower = city.lower()
    for location in LOCATIONS_DB:
        if location.city.lower() == city_lower:
            return location
    
    raise HTTPException(
        status_code=404,
        detail=f"Location for city '{city}' not found"
    )


@app.get("/locations/by-coordinates", response_model=LocationData, tags=["Locations"])
async def get_location_by_coordinates(
    latitude: float = Query(..., ge=-90, le=90, description="Latitude coordinate"),
    longitude: float = Query(..., ge=-180, le=180, description="Longitude coordinate"),
    tolerance: float = Query(0.5, ge=0, le=5, description="Search tolerance in degrees")
):
    """
    Find nearest location by coordinates within tolerance.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        tolerance: Maximum distance in degrees to consider a match (default: 0.5)
    
    Returns:
        Nearest location data within tolerance
    
    Raises:
        HTTPException: 404 if no location found within tolerance
    """
    for location in LOCATIONS_DB:
        lat_diff = abs(location.latitude - latitude)
        lon_diff = abs(location.longitude - longitude)
        
        if lat_diff <= tolerance and lon_diff <= tolerance:
            return location
    
    raise HTTPException(
        status_code=404,
        detail=f"No location found within {tolerance} degrees of ({latitude}, {longitude})"
    )


@app.get("/locations/by-country/{country}", response_model=list[LocationData], tags=["Locations"])
async def get_locations_by_country(country: str):
    """
    Get all locations in a specific country.
    
    Args:
        country: Country name (case-insensitive)
    
    Returns:
        List of locations in the specified country
    """
    country_lower = country.lower()
    results = [loc for loc in LOCATIONS_DB if loc.country.lower() == country_lower]
    
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No locations found for country '{country}'"
        )
    
    return results


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("LOCATION_SERVICE_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
