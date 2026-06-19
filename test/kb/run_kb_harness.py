from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from luoying_bot.capabilities.knowledge_base import KnowledgeBaseConfig, KnowledgeBaseService
from luoying_bot.capabilities.knowledge_base.analytics import KnowledgeAnalyticsEngine
from luoying_bot.capabilities.knowledge_base.answering import KnowledgeAnswerGenerator
from luoying_bot.capabilities.knowledge_base.embeddings import OpenAICompatibleEmbeddingProvider
from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolver
from luoying_bot.capabilities.knowledge_base.policy import KnowledgeBasePolicy
from luoying_bot.capabilities.knowledge_base.postgres_store import PostgresKnowledgeStore
from luoying_bot.capabilities.knowledge_base.query_agent import KBQueryAgent, KBQueryAgentConfig
from luoying_bot.capabilities.knowledge_base.semantic_layer import KnowledgeSemanticLayer
from luoying_bot.config import settings
from luoying_bot.infra.llm.openai_chat import OpenAICompatibleChatModel


DEFAULT_REPORT_DIR = Path("test/kb/reports")


@dataclass(slots=True)
class QueryCase:
    id: str
    question: str
    space_id: str | None
    top_k: int
    expected_any: list[str]
    expected_sources_any: list[str]
    min_citations: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryCase":
        return cls(
            id=str(data["id"]),
            question=str(data["question"]),
            space_id=(None if data.get("space_id") in (None, "") else str(data["space_id"]))
            if "space_id" in data
            else settings.kb_default_space_id,
            top_k=int(data.get("top_k") or 5),
            expected_any=[str(item) for item in data.get("expected_any", [])],
            expected_sources_any=[str(item) for item in data.get("expected_sources_any", [])],
            min_citations=int(data.get("min_citations") or 1),
        )


async def build_service(*, with_answer: bool) -> KnowledgeBaseService:
    query_model = OpenAICompatibleChatModel(
        settings.openai_base_url,
        settings.openai_api_key,
        settings.openai_model,
        settings.llm_temperature,
        settings.openai_enable_thinking,
    )
    store = PostgresKnowledgeStore(
        settings.kb_database_url,
        embedding_provider=OpenAICompatibleEmbeddingProvider(
            base_url=settings.kb_embedding_base_url,
            api_key=settings.kb_embedding_api_key,
            model=settings.kb_embedding_model,
            batch_size=settings.kb_embedding_batch_size,
        ),
        embedding_dimensions=settings.kb_embedding_dimensions,
    )
    await store.ensure_schema()
    query_agent = KBQueryAgent(
        rag_backend=store,
        structured_backend=store,
        analytics_engine=KnowledgeAnalyticsEngine(
            backend=store,
            value_backend=store,
            model=query_model,
            semantic_layer=KnowledgeSemanticLayer(),
        ),
        entity_resolver=EntityResolver(store),
        config=KBQueryAgentConfig(
            default_space_id=settings.kb_default_space_id,
        ),
    )
    return KnowledgeBaseService(
        structured_backend=store,
        query_agent=query_agent,
        answer_generator=KnowledgeAnswerGenerator(query_model if with_answer else None),
        config=KnowledgeBaseConfig(
            default_space_id=settings.kb_default_space_id,
            require_citation=settings.kb_require_citation,
        ),
        policy=KnowledgeBasePolicy(require_citation=settings.kb_require_citation),
    )


async def run_case(
    service: KnowledgeBaseService,
    case: QueryCase,
    *,
    with_answer: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    if with_answer:
        answer = await service.answer(
            question=case.question,
            space_id=case.space_id,
            platform="harness",
            conversation_id="kb-harness",
            user_id="kb-harness",
            top_k=case.top_k,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        text_blob = "\n".join(
            [
                answer.answer,
                *[citation.label() for citation in answer.citations],
                json.dumps(answer.data, ensure_ascii=False),
            ]
        )
        citations = answer.citations
        fallback_reason = answer.fallback_reason
        chunks_count = len(answer.data.get("chunks", [])) if isinstance(answer.data, dict) else 0
        structured_count = (
            len(answer.data.get("structured_records", [])) if isinstance(answer.data, dict) else 0
        )
    else:
        retrieval = await service.search(
            query_text=case.question,
            space_id=case.space_id,
            top_k=case.top_k,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        text_blob = "\n".join(
            [
                *[record.text() for record in retrieval.structured_records],
                *[chunk.text for chunk in retrieval.chunks],
                *[citation.label() for citation in retrieval.citations()],
            ]
        )
        citations = retrieval.citations()
        fallback_reason = retrieval.fallback_reason
        chunks_count = len(retrieval.chunks)
        structured_count = len(retrieval.structured_records)

    matched_terms = [term for term in case.expected_any if term and term in text_blob]
    matched_sources = [
        source for source in case.expected_sources_any if source and source in text_blob
    ]
    observed_citations = [
        {
            "title": citation.title,
            "source": citation.source,
            "score": getattr(citation, "metadata", {}).get("score"),
            "title_score": getattr(citation, "metadata", {}).get("title_score"),
            "phrase_score": getattr(citation, "metadata", {}).get("phrase_score"),
            "lexical_score": getattr(citation, "metadata", {}).get("lexical_score"),
            "vector_score": getattr(citation, "metadata", {}).get("vector_score"),
            "embedding_model": getattr(citation, "metadata", {}).get("embedding_model"),
        }
        for citation in citations[:5]
    ]
    term_ok = not case.expected_any or bool(matched_terms)
    source_ok = not case.expected_sources_any or bool(matched_sources)
    citation_ok = len(citations) >= case.min_citations
    ok = term_ok and source_ok and citation_ok and not fallback_reason
    return {
        "id": case.id,
        "question": case.question,
        "ok": ok,
        "latency_ms": elapsed_ms,
        "chunks_count": chunks_count,
        "structured_count": structured_count,
        "citations_count": len(citations),
        "observed_citations": observed_citations,
        "matched_terms": matched_terms,
        "matched_sources": matched_sources,
        "term_ok": term_ok,
        "source_ok": source_ok,
        "citation_ok": citation_ok,
        "fallback_reason": fallback_reason,
    }


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    service = await build_service(with_answer=args.with_answer)
    case = QueryCase(
        id="smoke_undergraduate_training",
        question=args.question,
        space_id=args.space_id,
        top_k=args.top_k,
        expected_any=["本科生培养", "人工智能"],
        expected_sources_any=[],
        min_citations=1,
    )
    result = await run_case(service, case, with_answer=args.with_answer)
    return {
        "type": "smoke",
        "ok": result["ok"],
        "settings": safe_settings_snapshot(),
        "results": [result],
    }


async def run_eval(args: argparse.Namespace) -> dict[str, Any]:
    cases = load_cases(Path(args.cases))
    service = await build_service(with_answer=args.with_answer)
    results = []
    for case in cases:
        results.append(await run_case(service, case, with_answer=args.with_answer))
    return {
        "type": "eval",
        "ok": all(item["ok"] for item in results),
        "settings": safe_settings_snapshot(),
        "summary": summarize_results(results),
        "results": results,
    }


async def run_perf(args: argparse.Namespace) -> dict[str, Any]:
    cases = load_cases(Path(args.cases))
    service = await build_service(with_answer=False)
    semaphore = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []
    request_failures: list[dict[str, Any]] = []
    quality_failures: list[dict[str, Any]] = []

    async def worker(index: int) -> None:
        case = cases[index % len(cases)]
        async with semaphore:
            try:
                result = await run_case(service, case, with_answer=False)
                latencies.append(float(result["latency_ms"]))
                if not result["ok"]:
                    quality_failures.append(result)
            except Exception as exc:
                request_failures.append(
                    {
                        "id": case.id,
                        "question": case.question,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    started = time.perf_counter()
    await asyncio.gather(*(worker(index) for index in range(args.iterations)))
    elapsed_sec = time.perf_counter() - started
    return {
        "type": "perf",
        "ok": not request_failures,
        "settings": safe_settings_snapshot(),
        "concurrency": args.concurrency,
        "iterations": args.iterations,
        "elapsed_sec": round(elapsed_sec, 3),
        "throughput_qps": round(args.iterations / elapsed_sec, 3) if elapsed_sec else None,
        "latency": summarize_latencies(latencies),
        "request_failures": request_failures[:20],
        "request_failure_count": len(request_failures),
        "quality_failures": quality_failures[:20],
        "quality_failure_count": len(quality_failures),
    }


def load_cases(path: Path) -> list[QueryCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("cases file must be a JSON array")
    return [QueryCase.from_dict(item) for item in data if isinstance(item, dict)]


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(item["latency_ms"]) for item in results]
    return {
        "total": len(results),
        "passed": sum(1 for item in results if item["ok"]),
        "failed": sum(1 for item in results if not item["ok"]),
        "pass_rate": round(sum(1 for item in results if item["ok"]) / len(results), 4)
        if results
        else 0,
        "latency": summarize_latencies(latencies),
    }


def summarize_latencies(latencies: list[float]) -> dict[str, Any]:
    if not latencies:
        return {"count": 0}
    ordered = sorted(latencies)
    return {
        "count": len(ordered),
        "min_ms": round(ordered[0], 2),
        "p50_ms": percentile(ordered, 0.50),
        "p90_ms": percentile(ordered, 0.90),
        "p95_ms": percentile(ordered, 0.95),
        "max_ms": round(ordered[-1], 2),
        "mean_ms": round(statistics.fmean(ordered), 2),
    }


def percentile(ordered: list[float], ratio: float) -> float:
    if len(ordered) == 1:
        return round(ordered[0], 2)
    index = (len(ordered) - 1) * ratio
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    value = ordered[lower] * (1 - fraction) + ordered[upper] * fraction
    return round(value, 2)


def safe_settings_snapshot() -> dict[str, Any]:
    return {
        "kb_artifact_root": str(settings.kb_artifact_root),
        "kb_database_url": settings.kb_database_url,
        "kb_default_space_id": settings.kb_default_space_id,
        "kb_require_citation": settings.kb_require_citation,
        "kb_embedding_base_url": settings.kb_embedding_base_url,
        "kb_embedding_model": settings.kb_embedding_model,
        "kb_embedding_batch_size": settings.kb_embedding_batch_size,
        "kb_embedding_dimensions": settings.kb_embedding_dimensions,
    }


def write_report(report: dict[str, Any], output: str | None) -> Path:
    if output:
        path = Path(output)
    else:
        DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = DEFAULT_REPORT_DIR / f"{report['type']}_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LuoYing KB smoke, quality, and performance tests")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser("smoke")
    smoke.add_argument("--question", default="武汉大学人工智能学院本科生培养有哪些信息？")
    smoke.add_argument("--space-id", default="sai")
    smoke.add_argument("--top-k", type=int, default=5)
    smoke.add_argument("--with-answer", action="store_true")
    smoke.add_argument("--output", default=None)

    eval_parser = subparsers.add_parser("eval")
    eval_parser.add_argument("--cases", default="test/kb/cases/sai_whu_core.json")
    eval_parser.add_argument("--with-answer", action="store_true")
    eval_parser.add_argument("--output", default=None)

    perf = subparsers.add_parser("perf")
    perf.add_argument("--cases", default="test/kb/cases/sai_whu_core.json")
    perf.add_argument("--concurrency", type=int, default=4)
    perf.add_argument("--iterations", type=int, default=20)
    perf.add_argument("--output", default=None)
    return parser


async def async_main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "smoke":
        report = await run_smoke(args)
    elif args.command == "eval":
        report = await run_eval(args)
    elif args.command == "perf":
        report = await run_perf(args)
    else:
        raise ValueError(f"unknown command: {args.command}")

    report["created_at"] = datetime.now().isoformat(timespec="seconds")
    path = write_report(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report={path}")
    return 0 if report["ok"] else 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
