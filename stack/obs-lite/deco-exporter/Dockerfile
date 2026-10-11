FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY exporter.py .
ENV DECO_STATE=/var/lib/deco-exporter/state.json
ENV DECO_EXPORTER_PORT=9105
EXPOSE 9105
CMD ["python", "-u", "exporter.py"]
