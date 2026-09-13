-- AI & Data Agent Evaluation - Database Schema
-- Medallion Architecture: Bronze → Silver → Gold

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- BRONZE LAYER: Raw Data (agent_interactions)
-- ============================================================================
-- Stores raw interactions from the agent without transformation
-- This is the landing zone for all agent activity

CREATE TABLE IF NOT EXISTS agent_interactions (
    interaction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id VARCHAR(100) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    user_query TEXT NOT NULL,
    agent_response TEXT,
    llm_model VARCHAR(50),
    tokens_used INTEGER CHECK (tokens_used >= 0),
    response_time_ms INTEGER CHECK (response_time_ms >= 0),
    sentiment VARCHAR(20),
    urgency_level VARCHAR(20),
    raw_metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for Bronze layer
CREATE INDEX IF NOT EXISTS idx_agent_interactions_transaction_id 
    ON agent_interactions(transaction_id);
CREATE INDEX IF NOT EXISTS idx_agent_interactions_user_id 
    ON agent_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_interactions_timestamp 
    ON agent_interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_agent_interactions_created_at 
    ON agent_interactions(created_at);

-- ============================================================================
-- SILVER LAYER: Cleaned and Enriched Data (enriched_transactions)
-- ============================================================================
-- Stores validated and enriched transaction data
-- Includes location enrichment from MCP Server

CREATE TABLE IF NOT EXISTS enriched_transactions (
    id SERIAL PRIMARY KEY,
    interaction_id UUID REFERENCES agent_interactions(interaction_id) ON DELETE CASCADE,
    user_id VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    city VARCHAR(100),
    country VARCHAR(100),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    timezone VARCHAR(100),
    weather_condition VARCHAR(50),
    temperature DECIMAL(5, 2),
    humidity INTEGER CHECK (humidity >= 0 AND humidity <= 100),
    wind_speed DECIMAL(5, 2),
    observations TEXT[],
    population BIGINT,
    language VARCHAR(200),
    currency VARCHAR(10),
    is_valid BOOLEAN DEFAULT TRUE,
    validation_errors TEXT[],
    processed_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for Silver layer
CREATE INDEX IF NOT EXISTS idx_enriched_transactions_interaction_id 
    ON enriched_transactions(interaction_id);
CREATE INDEX IF NOT EXISTS idx_enriched_transactions_user_id 
    ON enriched_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_enriched_transactions_timestamp 
    ON enriched_transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_enriched_transactions_city 
    ON enriched_transactions(city);
CREATE INDEX IF NOT EXISTS idx_enriched_transactions_country 
    ON enriched_transactions(country);
CREATE INDEX IF NOT EXISTS idx_enriched_transactions_is_valid 
    ON enriched_transactions(is_valid);

-- ============================================================================
-- GOLD LAYER: Aggregated Analytics (analytics_metrics)
-- ============================================================================
-- Stores pre-aggregated metrics for dashboard consumption
-- Optimized for analytical queries

CREATE TABLE IF NOT EXISTS analytics_metrics (
    id SERIAL PRIMARY KEY,
    metric_date DATE NOT NULL,
    city VARCHAR(100),
    country VARCHAR(100),
    total_transactions INTEGER DEFAULT 0,
    avg_response_time_ms DECIMAL(10, 2),
    total_tokens_used BIGINT DEFAULT 0,
    unique_users INTEGER DEFAULT 0,
    most_common_query_type VARCHAR(100),
    peak_hour INTEGER CHECK (peak_hour >= 0 AND peak_hour <= 23),
    avg_temperature DECIMAL(5, 2),
    most_common_weather VARCHAR(50),
    positive_sentiment_count INTEGER DEFAULT 0,
    neutral_sentiment_count INTEGER DEFAULT 0,
    negative_sentiment_count INTEGER DEFAULT 0,
    high_urgency_count INTEGER DEFAULT 0,
    medium_urgency_count INTEGER DEFAULT 0,
    low_urgency_count INTEGER DEFAULT 0,
    aggregated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(metric_date, city)
);

-- Indexes for Gold layer
CREATE INDEX IF NOT EXISTS idx_analytics_metrics_metric_date 
    ON analytics_metrics(metric_date);
CREATE INDEX IF NOT EXISTS idx_analytics_metrics_city 
    ON analytics_metrics(city);
CREATE INDEX IF NOT EXISTS idx_analytics_metrics_country 
    ON analytics_metrics(country);

-- ============================================================================
-- HELPER VIEWS
-- ============================================================================

-- View: Recent transactions with enrichment
CREATE OR REPLACE VIEW v_recent_enriched_transactions AS
SELECT 
    ai.transaction_id,
    ai.user_id,
    ai.timestamp,
    ai.user_query,
    ai.llm_model,
    ai.tokens_used,
    ai.response_time_ms,
    et.city,
    et.country,
    et.weather_condition,
    et.temperature,
    et.is_valid
FROM agent_interactions ai
LEFT JOIN enriched_transactions et ON ai.interaction_id = et.interaction_id
ORDER BY ai.timestamp DESC
LIMIT 100;

-- View: Daily summary statistics
CREATE OR REPLACE VIEW v_daily_summary AS
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as total_transactions,
    COUNT(DISTINCT user_id) as unique_users,
    AVG(tokens_used) as avg_tokens,
    AVG(response_time_ms) as avg_response_time,
    MIN(timestamp) as first_transaction,
    MAX(timestamp) as last_transaction
FROM agent_interactions
GROUP BY DATE(timestamp)
ORDER BY date DESC;

-- View: Location statistics
CREATE OR REPLACE VIEW v_location_stats AS
SELECT 
    et.city,
    et.country,
    COUNT(*) as transaction_count,
    AVG(ai.response_time_ms) as avg_response_time,
    SUM(ai.tokens_used) as total_tokens,
    COUNT(DISTINCT ai.user_id) as unique_users,
    AVG(et.temperature) as avg_temperature
FROM enriched_transactions et
JOIN agent_interactions ai ON et.interaction_id = ai.interaction_id
WHERE et.is_valid = TRUE
GROUP BY et.city, et.country
ORDER BY transaction_count DESC;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE agent_interactions IS 'Bronze Layer: Raw agent interaction data';
COMMENT ON TABLE enriched_transactions IS 'Silver Layer: Cleaned and enriched transaction data with location context';
COMMENT ON TABLE analytics_metrics IS 'Gold Layer: Pre-aggregated metrics for analytics dashboard';

COMMENT ON COLUMN agent_interactions.raw_metadata IS 'Original location metadata from transaction';
COMMENT ON COLUMN agent_interactions.sentiment IS 'LLM-analyzed sentiment: positive, neutral, negative';
COMMENT ON COLUMN agent_interactions.urgency_level IS 'LLM-detected urgency: low, medium, high';
COMMENT ON COLUMN enriched_transactions.observations IS 'Contextual observations from location service';
COMMENT ON COLUMN enriched_transactions.validation_errors IS 'List of validation errors if is_valid = FALSE';
COMMENT ON COLUMN analytics_metrics.most_common_query_type IS 'Classification of most frequent query type';

-- Grant permissions to agent_user (adjust as needed)
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO agent_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agent_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_user;
