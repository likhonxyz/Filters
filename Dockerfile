# Python slim image নিলাম যাতে size ছোট হয়
FROM python:3.11-slim

# কাজ করার directory
WORKDIR /app

# Dependencies আগে কপি করি (cache reuse হবে)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# বাকি source code কপি করি
COPY . .

# Persistent data directory (filters.sqlite, ইত্যাদি এখানে থাকবে)
VOLUME ["/data"]

# Env variable default
ENV BOT_DATA_DIR=/data

# Container run হলে main.py চালু হবে
CMD ["python", "main.py"]
