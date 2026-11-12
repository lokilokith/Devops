# Deployment Guide

OpsForge is designed to be deployed as a containerized workload using Docker.

## Production Requirements
- **Database**: PostgreSQL 14+ is highly recommended for production workloads. SQLite is used strictly for development and testing.
- **Environment Variables**: A secure .env file must be provided. Do not use default JWT secrets in production.

## Docker Deployment
\\\ash
docker-compose -f docker-compose.yml up -d --build
\\\

## WSGI Server
OpsForge uses gunicorn as its production WSGI HTTP server, which is bundled inside the provided Dockerfile.
