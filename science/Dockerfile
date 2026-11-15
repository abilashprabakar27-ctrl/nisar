FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Install the project's dependencies from pyproject.toml. The project is not pip-installed:
# its flat layout has several top-level packages, which setuptools refuses to package.
COPY pyproject.toml ./
RUN python -c "import tomllib, subprocess, sys; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *deps])"

# Copy only the code and catalog the API needs. .env is deliberately not copied.
COPY api ./api
COPY methods ./methods
COPY science ./science
COPY server ./server
COPY workers ./workers
COPY data/catalog ./data/catalog

EXPOSE 8000
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
