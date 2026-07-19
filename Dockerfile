# Use Microsoft's official Playwright image (has Chromium and system dependencies pre-installed)
FROM mcr.microsoft.com/playwright:v1.40.0-jammy

# Install Python and Pip
RUN apt-get update && apt-get install -y python3 python3-pip

WORKDIR /app

# Copy python requirements from the backend directory and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source files into the container
COPY backend/ .

# Expose port and run Uvicorn
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
