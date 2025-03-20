# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (for example, ffmpeg for audio file conversion)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install all required Python packages from requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the Google credentials file into the container
COPY credentials.json .

# Set an environment variable for Google credentials
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json

# Copy the entire project content into the container at /app
COPY . .

# Expose port 8000 to the outside world
EXPOSE 8000

# Define an environment variable if additional configurations are needed
ENV PYTHONUNBUFFERED=1

# Run the application using Uvicorn, with main:app as the entry point
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
