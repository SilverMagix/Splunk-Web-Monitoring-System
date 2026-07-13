FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py generator.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 8001

CMD ["./entrypoint.sh"]
