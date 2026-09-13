"""
Transaction Service - Simulated service that sends transactions to the agent.

This service is PROVIDED to candidates - they should integrate it with their agent.
The service can run in two modes:
1. Continuous mode: Sends transactions at regular intervals
2. Manual mode: Provides API endpoints to trigger transaction generation
"""

import asyncio
import os
from typing import Optional

import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from transaction_service.data_generator import TransactionGenerator


# Data Models
class TransactionConfig(BaseModel):
    agent_endpoint: str = Field(..., description="URL endpoint where agent receives transactions")
    interval_seconds: int = Field(5, ge=1, description="Interval between transactions in seconds")
    batch_size: int = Field(1, ge=1, le=100, description="Number of transactions per batch")


class ServiceStatus(BaseModel):
    status: str
    is_running: bool
    transactions_sent: int
    agent_endpoint: Optional[str]
    interval_seconds: int


# Initialize FastAPI app
app = FastAPI(
    title="Transaction Service",
    description="Simulated service that generates and sends user transactions to the agent",
    version="1.0.0",
)


# Service state
class ServiceState:
    def __init__(self):
        self.generator = TransactionGenerator()
        self.is_running = False
        self.transactions_sent = 0
        self.agent_endpoint = os.getenv("AGENT_ENDPOINT", "http://localhost:8000/transactions")
        self.interval_seconds = int(os.getenv("TRANSACTION_SERVICE_INTERVAL", "5"))
        self.task: Optional[asyncio.Task] = None


state = ServiceState()


async def send_transaction_to_agent(transaction: dict) -> bool:
    """
    Send a transaction to the agent endpoint.
    
    Args:
        transaction: Transaction data to send
    
    Returns:
        True if successful, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                state.agent_endpoint,
                json=transaction
            )
            response.raise_for_status()
            print(f"✓ Sent transaction {transaction['transaction_id']} to agent")
            return True
    except httpx.HTTPError as e:
        print(f"✗ Failed to send transaction {transaction['transaction_id']}: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error sending transaction: {e}")
        return False


async def continuous_transaction_sender():
    """Background task that continuously sends transactions to the agent."""
    print(f"Starting continuous transaction sender (interval: {state.interval_seconds}s)")
    
    while state.is_running:
        try:
            # Generate transaction
            transaction = state.generator.generate_transaction()
            
            # Send to agent
            success = await send_transaction_to_agent(transaction)
            
            if success:
                state.transactions_sent += 1
            
            # Wait for next interval
            await asyncio.sleep(state.interval_seconds)
            
        except Exception as e:
            print(f"Error in continuous sender: {e}")
            await asyncio.sleep(state.interval_seconds)
    
    print("Continuous transaction sender stopped")


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "service": "Transaction Service",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/status", response_model=ServiceStatus, tags=["Control"])
async def get_status():
    """Get current service status."""
    return ServiceStatus(
        status="running" if state.is_running else "stopped",
        is_running=state.is_running,
        transactions_sent=state.transactions_sent,
        agent_endpoint=state.agent_endpoint,
        interval_seconds=state.interval_seconds,
    )


@app.post("/configure", tags=["Control"])
async def configure_service(config: TransactionConfig):
    """
    Configure the transaction service.
    
    Args:
        config: Service configuration
    
    Returns:
        Updated configuration
    """
    if state.is_running:
        raise HTTPException(
            status_code=400,
            detail="Cannot configure while service is running. Stop it first."
        )
    
    state.agent_endpoint = config.agent_endpoint
    state.interval_seconds = config.interval_seconds
    
    return {
        "message": "Configuration updated",
        "agent_endpoint": state.agent_endpoint,
        "interval_seconds": state.interval_seconds,
    }


@app.post("/start", tags=["Control"])
async def start_service(background_tasks: BackgroundTasks):
    """Start continuous transaction generation and sending."""
    if state.is_running:
        raise HTTPException(
            status_code=400,
            detail="Service is already running"
        )
    
    state.is_running = True
    background_tasks.add_task(continuous_transaction_sender)
    
    return {
        "message": "Transaction service started",
        "agent_endpoint": state.agent_endpoint,
        "interval_seconds": state.interval_seconds,
    }


@app.post("/stop", tags=["Control"])
async def stop_service():
    """Stop continuous transaction generation."""
    if not state.is_running:
        raise HTTPException(
            status_code=400,
            detail="Service is not running"
        )
    
    state.is_running = False
    
    return {
        "message": "Transaction service stopped",
        "transactions_sent": state.transactions_sent,
    }


@app.post("/send-one", tags=["Manual"])
async def send_single_transaction():
    """
    Manually generate and send a single transaction.
    
    Returns:
        The generated transaction and send status
    """
    transaction = state.generator.generate_transaction()
    success = await send_transaction_to_agent(transaction)
    
    if success:
        state.transactions_sent += 1
    
    return {
        "transaction": transaction,
        "sent": success,
        "agent_endpoint": state.agent_endpoint,
    }


@app.post("/send-batch", tags=["Manual"])
async def send_transaction_batch(count: int = 10):
    """
    Manually generate and send a batch of transactions.
    
    Args:
        count: Number of transactions to generate and send
    
    Returns:
        Batch results
    """
    if count < 1 or count > 100:
        raise HTTPException(
            status_code=400,
            detail="Batch count must be between 1 and 100"
        )
    
    transactions = state.generator.generate_batch(count)
    results = []
    
    for transaction in transactions:
        success = await send_transaction_to_agent(transaction)
        results.append({
            "transaction_id": transaction["transaction_id"],
            "sent": success
        })
        
        if success:
            state.transactions_sent += 1
        
        # Small delay between transactions
        await asyncio.sleep(0.1)
    
    successful = sum(1 for r in results if r["sent"])
    
    return {
        "total": count,
        "successful": successful,
        "failed": count - successful,
        "results": results,
    }


@app.post("/reset", tags=["Control"])
async def reset_counter():
    """Reset the transaction counter."""
    if state.is_running:
        raise HTTPException(
            status_code=400,
            detail="Cannot reset while service is running. Stop it first."
        )
    
    old_count = state.transactions_sent
    state.transactions_sent = 0
    state.generator.reset_counter()
    
    return {
        "message": "Counter reset",
        "previous_count": old_count,
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("TRANSACTION_SERVICE_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
