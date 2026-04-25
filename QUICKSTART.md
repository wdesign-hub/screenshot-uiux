# Quick Start

```bash
docker build -t shots .
docker run --rm -v $(pwd)/out:/out shots --site https://example.com --out /out/site
```