<p align="center">
  <img src="assets/logo.png" width="180">
</p>

<h1 align="center">OntoAgent</h1>

<p align="center">
Knowledge-Driven Agent Framework
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.12-blue)

![LangGraph](https://img.shields.io/badge/LangGraph-Agent-green)

![Neo4j](https://img.shields.io/badge/Neo4j-Graph-orange)

![MCP](https://img.shields.io/badge/MCP-Enabled-purple)

Build AI Agents with:

\- LangGraph Workflow
\- MCP Tool Ecosystem
\- Knowledge Graph (Neo4j)
\- Ontology-based Reasoning
\- Agent Evaluation Harness

\---

\## Why OntoAgent?

User
↓
Agent
↓
Ontology
↓
Knowledge Graph
↓
Reasoning
↓
Tool

making agents more explainable, structured and scalable.

## architecture

┌─────────────┐
│ User                                    │
└──────┬──────┘
       │
┌──────▼──────┐
│ OntoAgent                       │
│ (LangGraph) │
└──────┬──────┘
       │
 ┌─────┴─────┐
 │ MCP Layer │
 └─────┬─────┘
       │
 ┌─────┼─────┐
 │     │     │
 ▼     ▼     ▼

Neo4j  Ontology  External APIs
Graph                     / Tools

## features

✅ LangGraph Workflow

✅ MCP Integration

✅ Neo4j Knowledge Graph

✅ Ontology Support

✅ FastAPI Service

🚧 Evaluation Harness

🚧 Docker Deployment

🚧 Multi-Agent Support

Quick Start

git clone ...

cp .env.example .env

docker compose up

python run.py

##Demo

Question:

Find all products purchased by a customer.

Answer:

...

![alt text](./docs/images/image.png)

![alt text](./docs/images/image-1.png)

![alt text](./docs/images/e3c9c66e34854e6816dffb4b9fdc66a5.png)

![alt text](./docs/images/5c7132b9260f40197e52c3703c15c4a1.png)

![alt text](./docs/images/d8aa2620e65794798931547b4a5fefbb.png)

![alt text](./docs/images/5a88da4abeef5dc25db81a3ef8670309.png)

![alt text](./docs/images/4705eef702c2aa9ffda509b17807969b.png)

![alt text](./docs/images/0cc6511b5f519d58d4af73517c491be2.png)

![alt text](./docs/images/4d241618b8b39e260dcc87b39a1940eb.png)

##Documentation

docs/

architecture/
├── mcp.md
├── agent-api.md
├── web-integration.md

ecosystem/
├── a2a.md
├── platform-strategy.md
├── agent-economy.md
