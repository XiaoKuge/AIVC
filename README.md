# AI VC Knowledge Graph

Track AI venture capital investment relationships using a NetworkX-based knowledge graph.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Seed the graph from XLSX data
python scripts/seed.py

# Query the graph
python scripts/query_cli.py stats
python scripts/query_cli.py portfolio "Andreessen Horowitz (a16z)"
python scripts/query_cli.py investors OpenAI
python scripts/query_cli.py co-investors "Sequoia Capital"
python scripts/query_cli.py search mistral
python scripts/query_cli.py details "Khosla Ventures"

# Generate interactive visualization
python viz/generate.py
# Open viz/output/graph.html in a browser

# Run incremental update (requires ANTHROPIC_API_KEY)
python scripts/update.py
python scripts/update.py --dry-run

# Run tests
pytest tests/ -v
```

## Graph Schema

**Nodes:** VCFirm, Company, Person

**Edges:** invested_in, partner_at, personal_investment

## Project Structure

```
aivc/          Core library (models, graph, ingest, query, export)
scrapers/      Incremental update scrapers (RSS, LLM, Crunchbase, VC websites)
data/          Graph JSON, aliases, raw XLSX, snapshots
viz/           Pyvis HTML visualization generator
scripts/       CLI tools (seed, query, update)
tests/         Pytest test suite
```
