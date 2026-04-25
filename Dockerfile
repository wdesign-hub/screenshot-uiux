FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

COPY screenshot_audit_v2.py /app/
RUN pip install --no-cache-dir playwright==1.45.0

ENV LANG=en_US.UTF-8
ENV TZ=UTC

ENTRYPOINT ["python", "/app/screenshot_audit_v2.py"]
