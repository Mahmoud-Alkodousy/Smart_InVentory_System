FROM python:3.11-slim

WORKDIR /app

# System deps
# fonts-dejavu-core / fonts-freefont-ttf: give reportlab an Arabic-capable
# TTF so the Auto Purchase Order PDF renders Arabic item/branch names
# correctly instead of falling back to tofu boxes (see reporting/purchase_order.py)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

RUN useradd -m app
USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
