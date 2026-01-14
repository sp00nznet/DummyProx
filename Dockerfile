# DummyProx - Multi-stage Docker Build
# Stage 1: Backend
FROM python:3.11-slim as backend

WORKDIR /app/backend

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Stage 2: Final image with nginx
FROM python:3.11-slim

# Install nginx and supervisor
RUN apt-get update && apt-get install -y \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy backend
WORKDIR /app
COPY --from=backend /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY backend/ /app/backend/

# Copy frontend
COPY frontend/ /var/www/html/

# Configure nginx
RUN rm /etc/nginx/sites-enabled/default
COPY nginx.conf /etc/nginx/sites-enabled/dummyprox

# Configure supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose port
EXPOSE 80

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
