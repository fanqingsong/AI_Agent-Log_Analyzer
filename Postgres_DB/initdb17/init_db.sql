-- Create the database
CREATE DATABASE chat_hist_db;

\connect chat_hist_db

-- Enable Vectorscale and pgvector extensions
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
