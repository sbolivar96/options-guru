# Portable deploy of the Options Guru backend API.
# Build context MUST be the repo root so the analytics modules are included.
#   docker build -t options-guru-api .
#   docker run -p 8000:8000 options-guru-api
FROM python:3.12-slim

WORKDIR /app

# Install backend + analytics dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the whole project (analytics modules live at the root next to backend/)
COPY . .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
