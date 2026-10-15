# Local setup

Tested on Windows 11 + WSL2 (Ubuntu). Works on any Linux or macOS with the same tools.

## Prerequisites
- Git, Docker (Docker Desktop with WSL integration on Windows)
- uv (https://docs.astral.sh/uv/) - installs Python 3.12 for the project
- Optional: Ollama (https://ollama.com) for local LLMs

Keep the repository on the Linux filesystem (e.g. ~/projects), not under /mnt/c.

## First run
~~~bash
git clone https://github.com/JAV8805/claimsight.git
cd claimsight
uv sync                      # create .venv and install locked dependencies
cp .env.example .env         # then edit the passwords in .env
make up                      # start Postgres (pgvector) and Redis
make test                    # run the test suite
make run                     # API at http://localhost:8000 (docs at /docs)
~~~

## Useful commands
| Command | What it does |
|---|---|
| make up / make down | Start / stop the local stack (data persists in the pgdata volume) |
| make ps | Show service status |
| make psql | SQL console in the database |
| make redis-cli | Redis console |
| make lint / make format | Check / fix style with ruff |

Services listen on 127.0.0.1 only. Never commit .env.
