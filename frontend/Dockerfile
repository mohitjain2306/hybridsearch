# frontend/Dockerfile

FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Only the packages the dashboard actually needs (subset of requirements.txt)
RUN pip install --no-cache-dir \
        streamlit==1.41.1 \
        plotly==5.24.1 \
        requests==2.32.3 \
        python-dotenv==1.0.1

COPY dashboard.py .

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "dashboard.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
