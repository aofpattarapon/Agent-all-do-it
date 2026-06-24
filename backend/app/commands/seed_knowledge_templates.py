"""Seed knowledge templates into the catalog."""

import asyncio

import click

from app.commands import command, info, success
from app.db.session import get_db_context
from app.repositories import knowledge_template as repo

# Curated knowledge base templates — high-quality reference documents
# that users can import into their projects.
KNOWLEDGE_TEMPLATES = [
    # Development Standards
    {
        "source": "curated",
        "source_key": "curated:python-pep8",
        "name": "Python PEP 8 Style Guide",
        "description": "Comprehensive Python coding standards and style conventions.",
        "category": "Development Standards",
        "subcategory": "Python",
        "content": """# Python PEP 8 Style Guide

## Code Layout
- Use 4 spaces per indentation level.
- Limit all lines to a maximum of 79 characters.
- Surround top-level function and class definitions with two blank lines.
- Method definitions inside a class are surrounded by a single blank line.

## Imports
- Imports should usually be on separate lines.
- Imports are always put at the top of the file, just after any module comments and docstrings.
- Group imports: standard library, third-party, local application.

## Naming Conventions
- `module_name`, `package_name`, `ClassName`, `method_name`, `ExceptionName`, `function_name`, `GLOBAL_CONSTANT_NAME`, `instance_var_name`, `function_parameter_name`, `local_var_name`.
- Use descriptive names.

## Comments
- Comments should be complete sentences.
- Block comments generally consist of one or more paragraphs built out of complete sentences.
- Use inline comments sparingly.
""",
        "tags": ["python", "coding-standards", "style-guide"],
        "popularity": 100,
    },
    {
        "source": "curated",
        "source_key": "curated:typescript-style",
        "name": "TypeScript Best Practices",
        "description": "TypeScript coding guidelines for type safety and maintainability.",
        "category": "Development Standards",
        "subcategory": "TypeScript",
        "content": """# TypeScript Best Practices

## Types
- Prefer `interface` over `type` for object shapes.
- Use explicit return types on exported functions.
- Avoid `any` — use `unknown` when the type is truly unknown.
- Use strict mode (`strict: true` in tsconfig).

## Naming
- PascalCase for types, interfaces, enums, and classes.
- camelCase for variables, functions, and methods.
- UPPER_SNAKE_CASE for constants.

## Functions
- Prefer arrow functions for callbacks.
- Use async/await over raw Promises.
- Destructure parameters when there are multiple arguments.

## Imports
- Use absolute imports for cross-module dependencies.
- Group and sort imports: built-in, external, internal.
""",
        "tags": ["typescript", "coding-standards", "best-practices"],
        "popularity": 95,
    },
    {
        "source": "curated",
        "source_key": "curated:rest-api-design",
        "name": "REST API Design Guidelines",
        "description": "Best practices for designing clean, scalable REST APIs.",
        "category": "Development Standards",
        "subcategory": "API Design",
        "content": """# REST API Design Guidelines

## URL Structure
- Use nouns, not verbs, in URIs.
- Use plural nouns for collections (`/users`, `/orders`).
- Keep URLs flat when possible.

## HTTP Methods
- GET: read
- POST: create
- PUT: full update
- PATCH: partial update
- DELETE: remove

## Status Codes
- 200 OK — successful GET/PUT/PATCH
- 201 Created — successful POST
- 204 No Content — successful DELETE
- 400 Bad Request — client error
- 401 Unauthorized — authentication required
- 403 Forbidden — permission denied
- 404 Not Found — resource missing
- 500 Internal Server Error — server fault

## Responses
- Use consistent response envelope.
- Include pagination metadata for lists.
- Return structured error objects.
""",
        "tags": ["api", "rest", "design", "backend"],
        "popularity": 90,
    },
    # AI / LLM
    {
        "source": "curated",
        "source_key": "curated:prompt-engineering",
        "name": "Prompt Engineering Guide",
        "description": "Techniques for crafting effective LLM prompts.",
        "category": "AI / LLM",
        "subcategory": "Prompt Engineering",
        "content": """# Prompt Engineering Guide

## Core Principles
1. **Be specific** — vague prompts yield vague answers.
2. **Provide context** — background information improves relevance.
3. **Use examples** — few-shot prompting boosts accuracy.
4. **Break complex tasks** — chain of thought for reasoning.

## Techniques
- **Zero-shot**: Direct instruction without examples.
- **Few-shot**: 2-5 examples before the actual query.
- **Chain-of-Thought**: Ask the model to think step by step.
- **Role Prompting**: Assign a persona (e.g., "You are a senior developer").
- **Output Formatting**: Request JSON, markdown, or structured data explicitly.

## Anti-patterns
- Don't overload a single prompt.
- Don't assume the model knows proprietary context.
- Don't ignore token limits.
""",
        "tags": ["ai", "llm", "prompt-engineering", "nlp"],
        "popularity": 120,
    },
    {
        "source": "curated",
        "source_key": "curated:agent-design-patterns",
        "name": "AI Agent Design Patterns",
        "description": "Common architectural patterns for building autonomous AI agents.",
        "category": "AI / LLM",
        "subcategory": "Agent Architecture",
        "content": """# AI Agent Design Patterns

## ReAct (Reasoning + Acting)
Alternate between reasoning steps and tool calls. Best for multi-step tasks.

## Plan-and-Execute
1. Generate a plan of sub-tasks.
2. Execute each sub-task sequentially or in parallel.
3. Verify results.

## Reflection / Self-Correction
- After generating output, critique it.
- Revise based on critique.
- Iterate until quality threshold is met.

## Multi-Agent Orchestration
- **Manager-Worker**: One agent delegates to specialists.
- **Peer Collaboration**: Multiple agents debate or vote.
- **Pipeline**: Output of agent A feeds agent B.

## Memory Strategies
- **Short-term**: In-context window (last N messages).
- **Long-term**: Vector DB + retrieval (RAG).
- **Episodic**: Summary of past task executions.
""",
        "tags": ["ai", "agents", "architecture", "patterns"],
        "popularity": 110,
    },
    # Business / Domain
    {
        "source": "curated",
        "source_key": "curated:agile-scrum",
        "name": "Agile Scrum Reference",
        "description": "Quick reference for Scrum ceremonies, roles, and artifacts.",
        "category": "Business",
        "subcategory": "Project Management",
        "content": """# Agile Scrum Reference

## Roles
- **Product Owner**: Defines what to build and prioritizes backlog.
- **Scrum Master**: Facilitates process, removes blockers.
- **Developers**: Self-organizing team that builds the product.

## Ceremonies
- **Sprint Planning**: Select backlog items for the sprint.
- **Daily Standup**: 15-min sync on progress and blockers.
- **Sprint Review**: Demo completed work to stakeholders.
- **Retrospective**: Reflect on process improvements.

## Artifacts
- **Product Backlog**: Ordered list of all desired work.
- **Sprint Backlog**: Items committed for current sprint.
- **Increment**: Sum of all completed backlog items.

## Metrics
- Velocity: Story points completed per sprint.
- Burndown: Remaining work over time.
- Cycle Time: Start to finish for a single item.
""",
        "tags": ["agile", "scrum", "project-management"],
        "popularity": 85,
    },
    {
        "source": "curated",
        "source_key": "curated:ddd-bounded-contexts",
        "name": "Domain-Driven Design: Bounded Contexts",
        "description": "Reference for identifying and modeling bounded contexts.",
        "category": "Business",
        "subcategory": "Software Architecture",
        "content": """# Domain-Driven Design: Bounded Contexts

## Definition
A bounded context is a explicit boundary within which a domain model applies. Outside the boundary, terms and concepts may have different meanings.

## Identifying Contexts
- Look for different vocabularies used by different teams.
- Track where business rules diverge.
- Follow organizational boundaries (Conway's Law).

## Context Mapping
- **Partnership**: Two contexts cooperate.
- **Shared Kernel**: Overlapping model subset shared explicitly.
- **Customer-Supplier**: One context consumes another's model.
- **Conformist**: Downstream accepts upstream model as-is.
- **Anti-corruption Layer**: Translate foreign model at boundary.
- **Open Host Service**: Publish clear API for multiple consumers.

## Tactical Patterns
- Aggregate: Cluster of entities/value objects with one root.
- Entity: Object with identity that changes over time.
- Value Object: Immutable, defined by attributes only.
- Domain Event: Something that happened in the domain.
""",
        "tags": ["ddd", "architecture", "domain-driven-design"],
        "popularity": 80,
    },
    # Security
    {
        "source": "curated",
        "source_key": "curated:owasp-top10",
        "name": "OWASP Top 10 Security Risks",
        "description": "Overview of the most critical web application security risks.",
        "category": "Security",
        "subcategory": "Web Security",
        "content": """# OWASP Top 10 Security Risks

## A01: Broken Access Control
- Enforce least privilege.
- Deny by default.
- Validate access server-side.

## A02: Cryptographic Failures
- Encrypt data in transit (TLS) and at rest.
- Use strong, modern algorithms.
- Don't hardcode secrets.

## A03: Injection
- Use parameterized queries.
- Validate and sanitize all inputs.
- Escape special characters.

## A04: Insecure Design
- Apply threat modeling.
- Use secure design patterns.
- Plan for failure.

## A05: Security Misconfiguration
- Harden default configurations.
- Minimize features and components.
- Regular patching.

## A06: Vulnerable Components
- Maintain software inventory.
- Use only maintained dependencies.
- Monitor CVEs.

## A07: Authentication Failures
- Implement MFA where possible.
- Use strong session management.
- Protect against brute force.

## A08: Data Integrity Failures
- Verify integrity of dependencies.
- Use digital signatures.

## A09: Logging Failures
- Log security-relevant events.
- Protect log integrity.
- Monitor and alert.

## A10: SSRF
- Validate and sanitize URLs.
- Deny by default for outbound requests.
""",
        "tags": ["security", "owasp", "web-security"],
        "popularity": 95,
    },
    # DevOps
    {
        "source": "curated",
        "source_key": "curated:docker-best-practices",
        "name": "Docker Best Practices",
        "description": "Guidelines for building efficient, secure Docker images.",
        "category": "DevOps",
        "subcategory": "Containerization",
        "content": """# Docker Best Practices

## Image Size
- Use minimal base images (alpine, distroless).
- Combine RUN commands where logical.
- Clean up package caches in the same layer.

## Security
- Don't run as root; use USER directive.
- Scan images for vulnerabilities.
- Pin base image versions with digests.
- Don't embed secrets in images.

## Build Performance
- Leverage build cache: order commands by change frequency.
- Use .dockerignore to reduce build context.
- Use multi-stage builds to separate build and runtime.

## Runtime
- Use read-only filesystems where possible.
- Set resource limits (CPU/memory).
- Health checks for service availability.
""",
        "tags": ["docker", "devops", "containers", "security"],
        "popularity": 88,
    },
    {
        "source": "curated",
        "source_key": "curated:ci-cd-patterns",
        "name": "CI/CD Pipeline Patterns",
        "description": "Reference for designing robust continuous integration and delivery pipelines.",
        "category": "DevOps",
        "subcategory": "Automation",
        "content": """# CI/CD Pipeline Patterns

## Pipeline Stages
1. **Build**: Compile, package, create artifacts.
2. **Test**: Unit, integration, security scans.
3. **Stage**: Deploy to pre-production.
4. **Approve**: Manual or automated gates.
5. **Deploy**: Release to production.

## Patterns
- **Trunk-based Development**: Short-lived branches, frequent merges.
- **Feature Flags**: Deploy incomplete features safely.
- **Blue-Green Deployment**: Zero-downtime with instant rollback.
- **Canary Releases**: Roll out to a subset of users first.
- **Immutable Infrastructure**: Replace, don't mutate.

## Quality Gates
- All tests must pass.
- Code coverage thresholds.
- Security scan clean.
- Performance regression checks.
""",
        "tags": ["ci-cd", "devops", "automation", "deployment"],
        "popularity": 82,
    },
    # Data
    {
        "source": "curated",
        "source_key": "curated:sql-style-guide",
        "name": "SQL Style Guide",
        "description": "SQL query formatting and optimization conventions.",
        "category": "Data",
        "subcategory": "SQL",
        "content": """# SQL Style Guide

## Formatting
- Use uppercase for keywords (SELECT, FROM, WHERE).
- One clause per line.
- Indent subqueries.
- Use meaningful table aliases.

## Naming
- snake_case for tables and columns.
- Singular for table names (`user`, not `users`) — or be consistent.
- Prefix indexes with `idx_`.

## Performance
- SELECT only needed columns.
- Use EXPLAIN ANALYZE to review query plans.
- Add indexes on foreign keys and frequently queried columns.
- Avoid SELECT * in production code.

## Safety
- Use parameterized queries — never concatenate SQL strings.
- Use transactions for multi-statement operations.
- Add LIMIT to exploratory queries.
""",
        "tags": ["sql", "database", "data", "style-guide"],
        "popularity": 78,
    },
    # Testing
    {
        "source": "curated",
        "source_key": "curated:testing-pyramid",
        "name": "Software Testing Pyramid",
        "description": "Reference for balanced test strategy across unit, integration, and E2E layers.",
        "category": "Testing",
        "subcategory": "Strategy",
        "content": """# Software Testing Pyramid

## Unit Tests (Base — 70%)
- Test individual functions/classes in isolation.
- Fast, deterministic, cheap to maintain.
- Use mocks for external dependencies.

## Integration Tests (Middle — 20%)
- Test component interactions.
- Verify database, API, and service boundaries.
- Slower than unit tests but catch interface bugs.

## E2E Tests (Top — 10%)
- Test complete user flows.
- Run against staging or production-like environments.
- Expensive and flaky — use sparingly.

## Additional Layers
- **Contract Tests**: Verify API consumer/provider agreements.
- **Performance Tests**: Load, stress, soak testing.
- **Security Tests**: SAST, DAST, dependency scanning.

## Principles
- Shift left: catch bugs as early as possible.
- Automate everything that can be automated.
- Maintain tests like production code.
""",
        "tags": ["testing", "quality", "automation", "strategy"],
        "popularity": 75,
    },
]


async def _seed_knowledge_templates(*, clear: bool = False) -> None:
    async with get_db_context() as db:
        if clear:
            from sqlalchemy import text

            await db.execute(text("DELETE FROM knowledge_templates WHERE source = 'curated'"))
            await db.commit()
            info("Cleared curated knowledge templates.")

        created = 0
        skipped = 0
        for tmpl in KNOWLEDGE_TEMPLATES:
            existing = await repo.get_by_source_key(db, tmpl["source_key"])
            if existing:
                skipped += 1
                continue
            await repo.create(db, **tmpl)
            created += 1

        await db.commit()
        success(f"Created {created} knowledge templates, skipped {skipped} (already exist).")


@command("seed-knowledge-templates", help="Seed knowledge template catalog into the database")
@click.option("--clear", is_flag=True, help="Delete existing curated templates before seeding")
def seed_knowledge_templates(clear: bool) -> None:
    """Seed the knowledge_templates table with curated reference documents."""
    asyncio.run(_seed_knowledge_templates(clear=clear))
