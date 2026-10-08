FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PIPI_CLOUD=1
ENV PIPI_DATA_DIR=/data
RUN mkdir -p /data
EXPOSE 5002
CMD ["sh","-c","gunicorn -w 1 -b 0.0.0.0:${PORT:-5002} --timeout 120 app:app"]
