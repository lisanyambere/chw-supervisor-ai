-- Creates the Langfuse database alongside the app database.
-- Runs automatically on first container start via docker-entrypoint-initdb.d.
CREATE DATABASE langfuse;
GRANT ALL PRIVILEGES ON DATABASE langfuse TO app;
